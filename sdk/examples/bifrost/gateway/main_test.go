package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"
	"testing"

	"github.com/maximhq/bifrost/core/schemas"
	"github.com/valyala/fasthttp"
)

type fixtureTransport func(*http.Request) (*http.Response, error)

func (f fixtureTransport) RoundTrip(request *http.Request) (*http.Response, error) { return f(request) }

func hookContext() *schemas.BifrostContext {
	ctx := schemas.NewBifrostContext(context.Background(), schemas.NoDeadline)
	ctx.SetValue(identityKey, "bifrost:test")
	ctx.SetValue(stateKey, &streamState{Request: jsonRequest(), Path: "/openai/v1/chat/completions"})
	return ctx
}

func jsonRequest() []byte { return []byte(`{"messages":[{"role":"user","content":"fixture"}]}`) }

func toolResponse() *schemas.HTTPResponse {
	return &schemas.HTTPResponse{
		StatusCode: 200,
		Body:       []byte(`{"choices":[{"message":{"tool_calls":[{"id":"native-call","function":{"name":"Write","arguments":"{}"}}]}}]}`),
		Headers:    map[string]string{"Content-Type": "text/event-stream", "content-length": "99999", "content-encoding": "gzip"},
	}
}

// assertWithheld checks what the pinned middleware actually applies; returning
// an error without replacing the response would leave its tool call deliverable.
func assertWithheld(t *testing.T, response *schemas.HTTPResponse, err error) {
	t.Helper()
	var client fasthttp.RequestCtx
	client.Response.Header.Set("Content-Encoding", "gzip")
	client.Response.Header.Set("Content-Length", "99999")
	client.SetStatusCode(response.StatusCode)
	for key, value := range response.Headers {
		client.Response.Header.Set(key, value)
	}
	if response.Body != nil {
		client.SetBody(response.Body)
	}
	var wire bytes.Buffer
	if _, err := client.Response.WriteTo(&wire); err != nil {
		t.Fatal(err)
	}
	var parsed fasthttp.Response
	if err := parsed.Read(bufio.NewReader(&wire)); err != nil {
		t.Fatal(err)
	}
	if parsed.StatusCode() != 403 || string(parsed.Body()) != `{"error":"Watcher withheld this response"}` {
		t.Fatalf("unsafe client response: status=%d body length=%d hook error=%v", parsed.StatusCode(), len(parsed.Body()), err)
	}
	if len(parsed.Header.ContentEncoding()) != 0 || string(parsed.Header.ContentType()) != "application/json" || parsed.Header.ContentLength() != len(parsed.Body()) {
		t.Fatalf("replacement retained incompatible headers: %s", parsed.Header.Header())
	}
}

func prohibitBridge(t *testing.T) {
	t.Helper()
	old := bridgeClient
	bridgeClient = &http.Client{Transport: fixtureTransport(func(_ *http.Request) (*http.Response, error) {
		t.Fatal("uncheckable response reached bridge")
		return nil, nil
	})}
	t.Cleanup(func() { bridgeClient = old })
}

func TestEmptyBufferedBodyWithheld(t *testing.T) {
	prohibitBridge(t)
	response := toolResponse()
	response.Body = nil
	assertWithheld(t, response, HTTPTransportPostHook(hookContext(), nil, response))
}

func TestOversizedBufferedBodyWithheld(t *testing.T) {
	prohibitBridge(t)
	response := toolResponse()
	response.Body = append(response.Body, bytes.Repeat([]byte(" "), 8*1024*1024+1)...)
	assertWithheld(t, response, HTTPTransportPostHook(hookContext(), nil, response))
}

func TestMissingRequestContextWithheld(t *testing.T) {
	prohibitBridge(t)
	response := toolResponse()
	ctx := hookContext()
	ctx.ClearValue(stateKey)
	assertWithheld(t, response, HTTPTransportPostHook(ctx, nil, response))
}

func TestNilRequestContextWithheld(t *testing.T) {
	prohibitBridge(t)
	response := toolResponse()
	ctx := hookContext()
	ctx.SetValue(stateKey, (*streamState)(nil))
	assertWithheld(t, response, HTTPTransportPostHook(ctx, nil, response))
}

func TestMissingResponseHeadersWithheld(t *testing.T) {
	prohibitBridge(t)
	response := toolResponse()
	response.Body = nil
	response.Headers = nil
	assertWithheld(t, response, HTTPTransportPostHook(hookContext(), nil, response))
}

func TestBridgeRefusalWithheld(t *testing.T) {
	old := bridgeClient
	bridgeClient = &http.Client{Transport: fixtureTransport(func(_ *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"action":"withhold"}`)), Header: make(http.Header)}, nil
	})}
	t.Cleanup(func() { bridgeClient = old })
	bridgeURL = "http://bridge.invalid"
	response := toolResponse()
	assertWithheld(t, response, HTTPTransportPostHook(hookContext(), nil, response))
}

func TestAppliedAllowPreservesResponse(t *testing.T) {
	old := bridgeClient
	calls := 0
	bridgeClient = &http.Client{Transport: fixtureTransport(func(_ *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"action":"release"}`)), Header: make(http.Header)}, nil
	})}
	t.Cleanup(func() { bridgeClient = old })
	bridgeURL = "http://bridge.invalid"
	response := toolResponse()
	original := append([]byte(nil), response.Body...)
	if err := HTTPTransportPostHook(hookContext(), nil, response); err != nil {
		t.Fatal(err)
	}
	if calls != 1 || response.StatusCode != 200 || !bytes.Equal(original, response.Body) || response.Headers["content-encoding"] != "gzip" {
		t.Fatal("applied allow changed the provider response or skipped the bridge")
	}
}

func TestProviderErrorPreserved(t *testing.T) {
	prohibitBridge(t)
	response := &schemas.HTTPResponse{StatusCode: 502, Body: []byte(`{"error":"provider unavailable"}`)}
	original := append([]byte(nil), response.Body...)
	if err := HTTPTransportPostHook(hookContext(), nil, response); err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != 502 || !bytes.Equal(original, response.Body) {
		t.Fatal("provider error changed")
	}
}

// fakeBridge answers every bridge call with status and body, recording the
// decoded envelopes and the endpoint each was sent to.
func fakeBridge(t *testing.T, status int, body string) *[]map[string]any {
	t.Helper()
	seen := &[]map[string]any{}
	old := bridgeClient
	bridgeClient = &http.Client{Transport: fixtureTransport(func(request *http.Request) (*http.Response, error) {
		var envelope map[string]any
		data, _ := io.ReadAll(request.Body)
		if err := json.Unmarshal(data, &envelope); err != nil {
			t.Fatal(err)
		}
		envelope["endpoint"] = request.URL.Path
		*seen = append(*seen, envelope)
		return &http.Response{StatusCode: status, Body: io.NopCloser(strings.NewReader(body)), Header: make(http.Header)}, nil
	})}
	t.Cleanup(func() { bridgeClient = old })
	bridgeURL = "http://bridge.invalid"
	return seen
}

func chatRequest(headers map[string]string) *schemas.HTTPRequest {
	all := map[string]string{"Content-Length": "52", "User-Agent": "fixture/1"}
	for key, value := range headers {
		all[key] = value
	}
	return &schemas.HTTPRequest{Method: "POST", Path: "/openai/v1/chat/completions", Headers: all, Query: map[string]string{}, Body: jsonRequest()}
}

func TestReplacementDeliveredAsSuccess(t *testing.T) {
	replacement := `{"id":"completion","choices":[{"index":0,"message":{"role":"assistant","content":"WATCHER NOTICE"},"finish_reason":"stop"}]}`
	seen := fakeBridge(t, 200, `{"action":"replace","response":`+replacement+`}`)
	response := toolResponse()
	if err := HTTPTransportPostHook(hookContext(), nil, response); err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != 200 || string(response.Body) != replacement {
		t.Fatalf("replacement not delivered: status=%d body=%s", response.StatusCode, response.Body)
	}
	if response.Headers["Content-Type"] != "application/json" || response.Headers["Content-Length"] != strconv.Itoa(len(replacement)) || response.Headers["Content-Encoding"] != "" {
		t.Fatalf("replacement kept provider headers: %v", response.Headers)
	}
	if _, stale := response.Headers["content-encoding"]; stale {
		t.Fatal("provider compression header survived")
	}
	if len(*seen) != 1 || (*seen)[0]["endpoint"] != "/evaluate" {
		t.Fatal("response was not evaluated exactly once")
	}
}

func TestPassthroughSkipsGrading(t *testing.T) {
	prohibitBridge(t)
	ctx := hookContext()
	ctx.SetValue(stateKey, &streamState{Passthrough: true})
	response := toolResponse()
	original := append([]byte(nil), response.Body...)
	if err := HTTPTransportPostHook(ctx, nil, response); err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != 200 || !bytes.Equal(original, response.Body) {
		t.Fatal("bridge's own alternative was changed")
	}
}

func TestPreHookInstallsNoticedBodyAndKeepsCredentials(t *testing.T) {
	noticed := `{"model":"fixture","messages":[{"role":"system","content":"notice"},{"role":"user","content":"fixture"}]}`
	seen := fakeBridge(t, 200, `{"action":"grade","request":`+noticed+`}`)
	ctx := schemas.NewBifrostContext(context.Background(), schemas.NoDeadline)
	request := chatRequest(map[string]string{"Authorization": "Bearer client", "X-Bf-Vk": "vk", "X-Bf-Api-Key": "selected", "x-bf-direct-key": "true", "Cookie": "private"})
	if response, err := HTTPTransportPreHook(ctx, request); err != nil || response != nil {
		t.Fatalf("unexpected pre-hook result: %v %v", response, err)
	}
	if string(request.Body) != noticed || request.Headers["Content-Length"] != strconv.Itoa(len(noticed)) {
		t.Fatalf("noticed body not installed: %s %v", request.Body, request.Headers)
	}
	envelope := (*seen)[0]
	if envelope["endpoint"] != "/validate" || envelope["marker"] != "" || envelope["body"] != base64.StdEncoding.EncodeToString(jsonRequest()) {
		t.Fatalf("validation envelope lost the exact body: %v", envelope)
	}
	state := ctx.Value(stateKey).(*streamState)
	if string(state.Request) != noticed || state.Passthrough {
		t.Fatal("Watcher snapshot differs from the provider request")
	}
	if len(state.Credentials) != 4 || state.Credentials["Authorization"] != "Bearer client" || state.Credentials["X-Bf-Vk"] != "vk" || state.Credentials["X-Bf-Api-Key"] != "selected" || state.Credentials["X-Bf-Direct-Key"] != "true" {
		t.Fatalf("unexpected credentials kept: %v", state.Credentials)
	}
}

func TestPreHookInstallsNoticedBodyUpToTheLimit(t *testing.T) {
	for _, size := range []int{limit, limit + 1} {
		prefix := `{"model":"fixture","pad":"`
		noticed := prefix + strings.Repeat("a", size-len(prefix)-2) + `"}`
		fakeBridge(t, 200, `{"action":"grade","request":`+noticed+`}`)
		request := chatRequest(nil)
		_, err := HTTPTransportPreHook(schemas.NewBifrostContext(context.Background(), schemas.NoDeadline), request)
		if size == limit && (err != nil || string(request.Body) != noticed) {
			t.Fatalf("a noticed body at the limit was not installed: %v", err)
		}
		if size > limit && (err == nil || string(request.Body) == noticed) {
			t.Fatal("a noticed body over the limit was installed")
		}
	}
}

func TestPreHookPassesValidMarkerAndBlanksIt(t *testing.T) {
	seen := fakeBridge(t, 200, `{"action":"passthrough"}`)
	ctx := schemas.NewBifrostContext(context.Background(), schemas.NoDeadline)
	request := chatRequest(map[string]string{"X-Watcher-Alternative": "123.abc"})
	if response, err := HTTPTransportPreHook(ctx, request); err != nil || response != nil {
		t.Fatalf("unexpected pre-hook result: %v %v", response, err)
	}
	if request.Headers["X-Watcher-Alternative"] != "" || !bytes.Equal(request.Body, jsonRequest()) {
		t.Fatal("marker reached the provider request or the body changed")
	}
	if (*seen)[0]["marker"] != "123.abc" || !ctx.Value(stateKey).(*streamState).Passthrough {
		t.Fatal("marker was not verified by the bridge")
	}
}

func TestPreHookRejectsInvalidMarker(t *testing.T) {
	fakeBridge(t, 403, `{"action":"reject"}`)
	ctx := schemas.NewBifrostContext(context.Background(), schemas.NoDeadline)
	response, err := HTTPTransportPreHook(ctx, chatRequest(map[string]string{"x-watcher-alternative": "1.forged"}))
	if err != nil || response == nil || response.StatusCode != 403 {
		t.Fatalf("forged marker accepted: %v %v", response, err)
	}
	if ctx.Value(stateKey) != nil {
		t.Fatal("rejected request kept exchange state")
	}
}

func TestPreHookRefusesGradeReplyForMarkedRequest(t *testing.T) {
	fakeBridge(t, 200, `{"action":"grade"}`)
	ctx := schemas.NewBifrostContext(context.Background(), schemas.NoDeadline)
	if _, err := HTTPTransportPreHook(ctx, chatRequest(map[string]string{"X-Watcher-Alternative": "1.x"})); err == nil {
		t.Fatal("marked request continued without a passthrough verdict")
	}
}

func TestPreHookRefusesUnsupportedRequest(t *testing.T) {
	fakeBridge(t, 200, `{"action":"reject"}`)
	ctx := schemas.NewBifrostContext(context.Background(), schemas.NoDeadline)
	if _, err := HTTPTransportPreHook(ctx, chatRequest(nil)); err == nil {
		t.Fatal("unsupported request reached the provider")
	}
}

func finishChunk(t *testing.T) *schemas.BifrostStreamChunk {
	t.Helper()
	var part schemas.BifrostChatResponse
	data := `{"id":"c","object":"chat.completion.chunk","model":"fixture","created":1,"choices":[{"index":0,"delta":{"content":"refused text","tool_calls":[{"index":0,"id":"native-call","type":"function","function":{"name":"Write","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}`
	if err := json.Unmarshal([]byte(data), &part); err != nil {
		t.Fatal(err)
	}
	return &schemas.BifrostStreamChunk{BifrostChatResponse: &part}
}

func streamContext() *schemas.BifrostContext {
	ctx := hookContext()
	ctx.Value(stateKey).(*streamState).Tools = map[int]map[string]any{}
	return ctx
}

func TestStreamReleasesReplacementInsteadOfRefusedCalls(t *testing.T) {
	replacement := `{"id":"c","object":"chat.completion","model":"fixture","created":1,"choices":[{"index":0,"message":{"role":"assistant","content":"refused text\n\nWATCHER NOTICE","tool_calls":[{"id":"alt-call","type":"function","function":{"name":"Read","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}`
	seen := fakeBridge(t, 200, `{"action":"replace","response":`+replacement+`}`)
	chunk, err := HTTPTransportStreamChunkHook(streamContext(), nil, finishChunk(t))
	if err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(chunk.BifrostChatResponse)
	text := string(encoded)
	if strings.Contains(text, "native-call") || !strings.Contains(text, "alt-call") || !strings.Contains(text, "WATCHER NOTICE") || !strings.Contains(text, `"delta"`) {
		t.Fatalf("stream did not carry the replacement: %s", text)
	}
	evaluated, _ := json.Marshal((*seen)[0]["response"])
	if !strings.Contains(string(evaluated), "native-call") {
		t.Fatal("the assembled proposal was not evaluated")
	}
}

func TestStreamWithheldOnBridgeRefusal(t *testing.T) {
	fakeBridge(t, 200, `{"action":"withhold"}`)
	if chunk, err := HTTPTransportStreamChunkHook(streamContext(), nil, finishChunk(t)); err == nil || chunk != nil {
		t.Fatal("refused stream released a chunk")
	}
}

func TestPassthroughStreamRejected(t *testing.T) {
	prohibitBridge(t)
	ctx := hookContext()
	ctx.SetValue(stateKey, &streamState{Passthrough: true})
	if chunk, err := HTTPTransportStreamChunkHook(ctx, nil, finishChunk(t)); err == nil || chunk != nil {
		t.Fatal("ungraded stream released a chunk")
	}
}

func TestAlternativeHeadersAddOnlyValidOperatorNames(t *testing.T) {
	names, err := alternativeHeaders(" X-Team-Project ,,")
	if err != nil || len(names) != len(baseForwardedHeaders)+1 || names[len(names)-1] != "X-Team-Project" {
		t.Fatalf("operator header not added: %v %v", names, err)
	}
	for _, bad := range []string{"Content-Length", "x-watcher-alternative", "bad header", "x:y"} {
		if _, err := alternativeHeaders(bad); err == nil {
			t.Fatalf("accepted %q", bad)
		}
	}
}

func TestPreHookKeepsSessionIdentityHeaders(t *testing.T) {
	fakeBridge(t, 200, `{"action":"grade"}`)
	ctx := schemas.NewBifrostContext(context.Background(), schemas.NoDeadline)
	request := chatRequest(map[string]string{"X-Bf-Session-Id": "explicit", "X-Claude-Code-Session-Id": "harness", "Session_id": "codex", "X-Other": "dropped"})
	if _, err := HTTPTransportPreHook(ctx, request); err != nil {
		t.Fatal(err)
	}
	kept := ctx.Value(stateKey).(*streamState).Credentials
	if len(kept) != 3 || kept["X-Bf-Session-Id"] != "explicit" || kept["X-Claude-Code-Session-Id"] != "harness" || kept["Session_id"] != "codex" {
		t.Fatalf("session identity not kept for alternatives: %v", kept)
	}
}

func TestStructuredOutputRefusalIsAnExplicitError(t *testing.T) {
	fakeBridge(t, 200, `{"action":"structured_refusal"}`)
	response := toolResponse()
	if err := HTTPTransportPostHook(hookContext(), nil, response); err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != 403 || string(response.Body) != string(structuredRefusalBody) || response.Headers["Content-Type"] != "application/json" {
		t.Fatalf("structured refusal not delivered as an error: %d %s", response.StatusCode, response.Body)
	}
	if chunk, err := HTTPTransportStreamChunkHook(streamContext(), nil, finishChunk(t)); !errors.Is(err, errStructuredRefusal) || chunk != nil {
		t.Fatalf("stream did not end with the structured refusal error: %v", err)
	}
}
