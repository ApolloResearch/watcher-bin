package main

import (
	"bufio"
	"bytes"
	"context"
	"io"
	"net/http"
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
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"verdict":false}`)), Header: make(http.Header)}, nil
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
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"verdict":true}`)), Header: make(http.Header)}, nil
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
