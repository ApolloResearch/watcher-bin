// Package main implements Bifrost's HTTP transport plugin ABI.
// It withholds client-visible function calls until the private SDK bridge returns
// an applied allow/deferred decision; callers cannot choose or disable policy.
// After a refusal the bridge returns a replacement completion (Watcher's notices
// plus an approved alternative or the model's final question to the user), which
// the plugin delivers instead of the refused response.
package main

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/maximhq/bifrost/core/schemas"
)

const limit = 8 * 1024 * 1024
const stateKey schemas.BifrostContextKey = "watcher-stream"
const identityKey schemas.BifrostContextKey = "watcher-conversation"

// alternativeHeader marks the bridge's own alternative request. Only the bridge
// can sign it; the plugin passes it to the bridge for verification.
const alternativeHeader = "X-Watcher-Alternative"

// baseForwardedHeaders are the headers Bifrost authenticates a client and selects
// its provider key by: virtual keys, bearer/API keys, a stored key chosen by name
// or ID, direct-key mode, and the session identity session affinity binds keys
// and routes to (x-bf-session-id with its TTL and switch, and the coding-harness
// session headers Bifrost falls back to, schemas.HarnessSessionHeaders). They are
// handed to the bridge, in memory only, so an alternative is generated as the
// same client with the same key, session binding, routing, budgets and isolation.
var baseForwardedHeaders = []string{
	"Authorization", "Api-Key", "X-Api-Key", "X-Goog-Api-Key", "X-Bf-Vk", "X-Bf-Api-Key", "X-Bf-Api-Key-Id", "X-Bf-Direct-Key",
	"X-Bf-Session-Id", "X-Bf-Session-Ttl", "X-Bf-Session-Affinity",
	"X-Claude-Code-Session-Id", "X-Session-Affinity", "X-Session-Id", "Session-Id", "Session_id", "Thread-Id", "Conversation_id",
}

// reservedHeaders describe the transport or the marker and are never forwarded.
var reservedHeaders = map[string]bool{"host": true, "content-length": true, "content-type": true, "content-encoding": true, "transfer-encoding": true, "connection": true, "accept-encoding": true, "x-watcher-alternative": true}

// forwardedHeaders is the base list plus WATCHER_ALTERNATIVE_HEADERS, set in Init.
var forwardedHeaders = baseForwardedHeaders

// alternativeHeaders adds operator-listed headers (comma-separated): the
// operator-defined headers Bifrost governance is configured to require.
func alternativeHeaders(extra string) ([]string, error) {
	names := append([]string(nil), baseForwardedHeaders...)
	for _, name := range strings.Split(extra, ",") {
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}
		for _, r := range name {
			if !(r == '-' || r >= '0' && r <= '9' || r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z') {
				return nil, errors.New("invalid WATCHER_ALTERNATIVE_HEADERS")
			}
		}
		if reservedHeaders[strings.ToLower(name)] {
			return nil, errors.New("invalid WATCHER_ALTERNATIVE_HEADERS")
		}
		names = append(names, name)
	}
	return names, nil
}

var bridgeURL string
var bridgeToken string

// The bridge's 420-second recovery deadline stays below this timeout.
var bridgeClient = &http.Client{Timeout: 425 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return errors.New("bridge redirects disabled") }}

// Init validates private deployment settings before Bifrost admits requests.
func Init(_ any) error {
	bridgeURL = os.Getenv("WATCHER_BRIDGE_URL")
	bridgeToken = os.Getenv("WATCHER_BRIDGE_TOKEN")
	parsed, err := url.Parse(bridgeURL)
	if err != nil || parsed.Host == "" || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || bridgeToken == "" {
		return errors.New("invalid private Watcher bridge configuration")
	}
	if forwardedHeaders, err = alternativeHeaders(os.Getenv("WATCHER_ALTERNATIVE_HEADERS")); err != nil {
		return err
	}
	bridgeURL = strings.TrimRight(bridgeURL, "/")
	return nil
}
func GetName() string { return "watcher" }
func Cleanup() error  { bridgeClient.CloseIdleConnections(); return nil }
func HTTPTransportPreAuthHook(_ *schemas.BifrostContext, _ *schemas.HTTPRequest) (*schemas.HTTPResponse, error) {
	return nil, nil
}

// bridgeReply is the bridge's answer. Action is "grade" or "passthrough" from
// /validate, and "release", "replace" or "withhold" from /evaluate. Request is
// the body to send upstream (when it changed); Response is a replacement
// completion. Both are kept as the bridge's exact bytes.
type bridgeReply struct {
	Action   string          `json:"action"`
	Request  json.RawMessage `json:"request"`
	Response json.RawMessage `json:"response"`
}

// consult posts one envelope to the bridge and returns its status and reply.
// The reply may hold a replacement completion, so it is bounded by the body
// limit plus room for the envelope.
func consult(endpoint string, payload map[string]any) (int, *bridgeReply, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return 0, nil, errors.New("invalid exchange")
	}
	req, err := http.NewRequest("POST", bridgeURL+endpoint, bytes.NewReader(encoded))
	if err != nil {
		return 0, nil, errors.New("invalid bridge endpoint")
	}
	req.Header.Set("Authorization", "Bearer "+bridgeToken)
	req.Header.Set("Content-Type", "application/json")
	reply, err := bridgeClient.Do(req)
	if err != nil {
		return 0, nil, errors.New("Watcher unavailable; response withheld")
	}
	defer reply.Body.Close()
	body, err := io.ReadAll(io.LimitReader(reply.Body, limit+65537))
	var decoded bridgeReply
	if err != nil || len(body) > limit+65536 || json.Unmarshal(body, &decoded) != nil {
		return reply.StatusCode, nil, errors.New("Watcher withheld this response")
	}
	return reply.StatusCode, &decoded, nil
}

func metadata(identity, path, userAgent string) map[string]string {
	return map[string]string{"watcher_conversation_id": identity, "watcher_url": path, "watcher_provider": "openai", "watcher_user_agent": userAgent}
}

// evaluate asks the bridge about a complete response and returns a replacement
// completion, or nil to release the response unchanged. Any other outcome is an
// error, and the caller withholds the response.
func evaluate(state *streamState, response json.RawMessage, identity string) (json.RawMessage, error) {
	status, reply, err := consult("/evaluate", map[string]any{"request": state.Request, "response": response, "metadata": metadata(identity, state.Path, state.UserAgent), "credentials": state.Credentials})
	if err != nil {
		return nil, err
	}
	if status == 200 && reply.Action == "release" {
		return nil, nil
	}
	if status == 200 && reply.Action == "replace" && len(reply.Response) > 0 && len(reply.Response) <= limit {
		return reply.Response, nil
	}
	if status == 200 && reply.Action == "structured_refusal" {
		return nil, errStructuredRefusal
	}
	return nil, errors.New("Watcher withheld this response")
}

// errStructuredRefusal reports a refusal in a request that asked for JSON
// output (response_format json_object or json_schema): a text notice would
// make that content unparseable, so the client gets an explicit error instead.
var errStructuredRefusal = errors.New("Watcher refused a tool call in this response, and its notice cannot be delivered inside the requested structured output format")

// structuredRefusalBody is errStructuredRefusal as an OpenAI-style error.
var structuredRefusalBody = []byte(`{"error":{"message":"Watcher refused a tool call in this response, and its notice cannot be delivered inside the requested structured output format","type":"watcher_withheld","code":403}}`)

func header(headers map[string]string, name string) (string, string) {
	for key, value := range headers {
		if strings.EqualFold(key, name) {
			return key, value
		}
	}
	return "", ""
}

// HTTPTransportPreHook validates the client-facing request before provider calls.
// A request without a marker gets Watcher's system notice installed by the
// bridge. A request with the bridge's valid marker is the bridge's own
// alternative: it passes through ungraded, with the marker blanked. Bifrost
// applies header changes with Set and offers no delete, so an empty value is
// how the marker is removed before Bifrost builds the provider request.
func HTTPTransportPreHook(ctx *schemas.BifrostContext, req *schemas.HTTPRequest) (*schemas.HTTPResponse, error) {
	if req.Method != "POST" || req.Path != "/openai/v1/chat/completions" || len(req.Query) > 0 {
		return nil, errors.New("only OpenAI Chat Completions is supported by this Watcher deployment")
	}
	if len(req.Body) > limit {
		return nil, errors.New("request exceeds Watcher example limit")
	}
	nonce := make([]byte, 16)
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}
	identity := "bifrost:" + hex.EncodeToString(nonce)
	ctx.SetValue(identityKey, identity)
	_, userAgent := header(req.Headers, "User-Agent")
	markerKey, marker := header(req.Headers, alternativeHeader)
	// The body travels as base64 so the bridge checks a marker against exact bytes.
	status, reply, err := consult("/validate", map[string]any{"body": req.Body, "marker": marker, "metadata": metadata(identity, req.Path, userAgent)})
	if status == http.StatusForbidden && marker != "" {
		body := []byte(`{"error":"Invalid Watcher alternative marker"}`)
		return &schemas.HTTPResponse{StatusCode: http.StatusForbidden, Body: body, Headers: map[string]string{"Content-Type": "application/json", "Content-Length": strconv.Itoa(len(body))}}, nil
	}
	if err != nil || status != 200 {
		return nil, errors.New("Watcher withheld this response")
	}
	if marker != "" {
		if reply.Action != "passthrough" {
			return nil, errors.New("Watcher withheld this response")
		}
		req.Headers[markerKey] = ""
		ctx.SetValue(stateKey, &streamState{Passthrough: true})
		return nil, nil
	}
	if reply.Action != "grade" {
		return nil, errors.New("Watcher withheld this response")
	}
	if len(reply.Request) > 0 {
		if len(reply.Request) > limit {
			return nil, errors.New("request exceeds Watcher example limit")
		}
		req.Body = append([]byte(nil), reply.Request...)
		if key, _ := header(req.Headers, "Content-Length"); key != "" {
			req.Headers[key] = strconv.Itoa(len(req.Body))
		}
	}
	credentials := map[string]string{}
	for _, name := range forwardedHeaders {
		if _, value := header(req.Headers, name); value != "" {
			credentials[name] = value
		}
	}
	// Streaming callbacks outlive the pooled HTTP request body.
	ctx.SetValue(stateKey, &streamState{Request: append(json.RawMessage(nil), req.Body...), Path: req.Path, UserAgent: userAgent, Credentials: credentials, Tools: make(map[int]map[string]any)})
	return nil, nil
}

// HTTPTransportPostHook checks the exact complete body before buffered delivery.
func HTTPTransportPostHook(ctx *schemas.BifrostContext, req *schemas.HTTPRequest, resp *schemas.HTTPResponse) error {
	state, ok := ctx.Value(stateKey).(*streamState)
	if ok && state != nil && state.Passthrough {
		// The bridge's own alternative: the bridge grades it before release.
		return nil
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil
	}
	if len(resp.Body) == 0 || len(resp.Body) > limit {
		withholdResponse(resp)
		return nil
	}
	identity, _ := ctx.Value(identityKey).(string)
	if resp.Headers == nil {
		resp.Headers = map[string]string{}
	}
	resp.Headers["X-Watcher-Conversation-Id"] = identity
	if !ok || state == nil {
		withholdResponse(resp)
		return nil
	}
	replacement, err := evaluate(state, resp.Body, identity)
	if errors.Is(err, errStructuredRefusal) {
		replaceBody(resp, http.StatusForbidden, structuredRefusalBody)
	} else if err != nil {
		withholdResponse(resp)
	} else if replacement != nil {
		replaceBody(resp, http.StatusOK, replacement)
	}
	return nil
}

// withholdResponse replaces the deliverable itself: Bifrost logs post-hook errors
// without withholding the body.
func withholdResponse(resp *schemas.HTTPResponse) {
	replaceBody(resp, http.StatusForbidden, []byte(`{"error":"Watcher withheld this response"}`))
}

// replaceBody installs a JSON body. Empty encoding clears any provider
// compression header when Bifrost copies these headers onto its existing HTTP
// response.
func replaceBody(resp *schemas.HTTPResponse, status int, body []byte) {
	resp.StatusCode = status
	resp.Body = body
	for key := range resp.Headers {
		if strings.EqualFold(key, "Content-Type") || strings.EqualFold(key, "Content-Length") || strings.EqualFold(key, "Content-Encoding") {
			delete(resp.Headers, key)
		}
	}
	if resp.Headers == nil {
		resp.Headers = map[string]string{}
	}
	resp.Headers["Content-Type"] = "application/json"
	resp.Headers["Content-Length"] = strconv.Itoa(len(resp.Body))
	resp.Headers["Content-Encoding"] = ""
}

type streamState struct {
	Request         json.RawMessage
	Path, UserAgent string
	Credentials     map[string]string
	Passthrough     bool
	Text, Refusal   string
	Tools           map[int]map[string]any
	Bytes           int
	Done            bool
}

// completionChunk re-encodes a complete chat.completion as the stream's one
// completion delta, so delivered bytes come only from an evaluated message.
func completionChunk(response map[string]any) (*schemas.BifrostStreamChunk, error) {
	choices, ok := response["choices"].([]any)
	if !ok || len(choices) != 1 {
		return nil, errors.New("invalid evaluated completion")
	}
	choice, ok := choices[0].(map[string]any)
	if !ok {
		return nil, errors.New("invalid evaluated completion")
	}
	message, ok := choice["message"].(map[string]any)
	if !ok {
		return nil, errors.New("invalid evaluated completion")
	}
	if value, present := message["tool_calls"]; present && value != nil {
		calls, ok := value.([]any)
		if !ok {
			return nil, errors.New("invalid evaluated completion")
		}
		for i, item := range calls {
			call, ok := item.(map[string]any)
			if !ok {
				return nil, errors.New("invalid evaluated completion")
			}
			call["index"] = i
		}
	}
	response["object"] = "chat.completion.chunk"
	response["choices"] = []any{map[string]any{"index": 0, "delta": message, "finish_reason": choice["finish_reason"]}}
	body, err := json.Marshal(response)
	if err != nil {
		return nil, err
	}
	var result schemas.BifrostChatResponse
	if err = json.Unmarshal(body, &result); err != nil {
		return nil, err
	}
	return &schemas.BifrostStreamChunk{BifrostChatResponse: &result}, nil
}

// HTTPTransportStreamChunkHook suppresses original chunks and releases one newly
// encoded, evaluated completion delta when the provider's finish marker arrives.
// After a refusal that delta carries the bridge's replacement completion. A
// missing marker, oversized stream or unsupported content releases no tools.
func HTTPTransportStreamChunkHook(ctx *schemas.BifrostContext, req *schemas.HTTPRequest, chunk *schemas.BifrostStreamChunk) (*schemas.BifrostStreamChunk, error) {
	state, ok := ctx.Value(stateKey).(*streamState)
	if !ok || state == nil || state.Passthrough || chunk.BifrostChatResponse == nil || chunk.BifrostError != nil {
		// The bridge requests alternatives buffered, so a passthrough stream is unexpected.
		return nil, errors.New("unsupported or failed provider stream")
	}
	raw, err := json.Marshal(chunk.BifrostChatResponse)
	if err != nil {
		return nil, err
	}
	state.Bytes += len(raw)
	if state.Bytes > limit {
		return nil, errors.New("stream exceeds Watcher example limit")
	}
	var part map[string]any
	if err = json.Unmarshal(raw, &part); err != nil {
		return nil, err
	}
	choices, ok := part["choices"].([]any)
	if !ok {
		return nil, errors.New("invalid stream choices")
	}
	if len(choices) == 0 {
		return nil, nil
	}
	if state.Done || len(choices) != 1 {
		return nil, errors.New("unexpected additional stream choice")
	}
	choice, ok := choices[0].(map[string]any)
	if !ok || choice["index"] != float64(0) {
		return nil, errors.New("invalid stream index")
	}
	delta, ok := choice["delta"].(map[string]any)
	if !ok {
		return nil, errors.New("missing stream delta")
	}
	for _, key := range []string{"audio", "function_call", "reasoning", "reasoning_content", "reasoning_details"} {
		if value := delta[key]; value != nil {
			return nil, errors.New("unsupported stream content")
		}
	}
	if value := delta["content"]; value != nil {
		text, ok := value.(string)
		if !ok {
			return nil, errors.New("non-text stream content")
		}
		state.Text += text
	}
	if value := delta["refusal"]; value != nil {
		text, ok := value.(string)
		if !ok {
			return nil, errors.New("invalid refusal")
		}
		state.Refusal += text
	}
	if value := delta["tool_calls"]; value != nil {
		calls, ok := value.([]any)
		if !ok {
			return nil, errors.New("invalid stream tools")
		}
		for _, item := range calls {
			call, ok := item.(map[string]any)
			if !ok {
				return nil, errors.New("invalid stream call")
			}
			n, ok := call["index"].(float64)
			if !ok || n < 0 || n >= limit || n != float64(int(n)) {
				return nil, errors.New("invalid stream call index")
			}
			index := int(n)
			target := state.Tools[index]
			if target == nil {
				target = map[string]any{"id": "", "type": "function", "function": map[string]any{"name": "", "arguments": ""}}
				state.Tools[index] = target
			}
			if typ := call["type"]; typ != nil && typ != "function" {
				return nil, errors.New("unsupported stream tool")
			}
			if id := call["id"]; id != nil {
				text, ok := id.(string)
				if !ok {
					return nil, errors.New("invalid stream call ID")
				}
				if target["id"] != "" && target["id"] != text {
					return nil, errors.New("changed stream call ID")
				}
				target["id"] = text
			}
			if value := call["function"]; value != nil {
				function, ok := value.(map[string]any)
				if !ok {
					return nil, errors.New("invalid stream function")
				}
				dest := target["function"].(map[string]any)
				for _, key := range []string{"name", "arguments"} {
					if v := function[key]; v != nil {
						text, ok := v.(string)
						if !ok {
							return nil, errors.New("invalid stream function fragment")
						}
						dest[key] = dest[key].(string) + text
					}
				}
			}
		}
	}
	finish := choice["finish_reason"]
	if finish == nil {
		return nil, nil
	}
	message := map[string]any{"role": "assistant", "content": state.Text}
	if state.Refusal != "" {
		message["refusal"] = state.Refusal
	}
	if len(state.Tools) > 0 {
		calls := make([]any, len(state.Tools))
		for i := range calls {
			call, ok := state.Tools[i]
			if !ok {
				return nil, errors.New("noncontiguous stream calls")
			}
			calls[i] = call
		}
		message["tool_calls"] = calls
	}
	response := map[string]any{"id": part["id"], "object": "chat.completion", "model": part["model"], "created": part["created"], "choices": []any{map[string]any{"index": 0, "message": message, "finish_reason": finish}}}
	body, err := json.Marshal(response)
	if err != nil {
		return nil, err
	}
	identity, _ := ctx.Value(identityKey).(string)
	replacement, err := evaluate(state, body, identity)
	if err != nil {
		return nil, err
	}
	// Re-encode solely from the message evaluated by Watcher or the bridge's
	// replacement, never replay held bytes.
	if replacement != nil {
		response = nil
		if err = json.Unmarshal(replacement, &response); err != nil || response == nil {
			return nil, errors.New("invalid evaluated completion")
		}
	}
	result, err := completionChunk(response)
	if err != nil {
		return nil, err
	}
	state.Done = true
	return result, nil
}
