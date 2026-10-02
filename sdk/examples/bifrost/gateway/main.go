// Package main implements Bifrost's HTTP transport plugin ABI.
// It withholds client-visible function calls until the private SDK bridge returns
// an applied allow/deferred decision; callers cannot choose or disable policy.
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

var bridgeURL string
var bridgeToken string
var bridgeClient = &http.Client{Timeout: 425 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return errors.New("bridge redirects disabled") }}

// Init validates private deployment settings before Bifrost admits requests.
func Init(_ any) error {
	bridgeURL = os.Getenv("WATCHER_BRIDGE_URL")
	bridgeToken = os.Getenv("WATCHER_BRIDGE_TOKEN")
	parsed, err := url.Parse(bridgeURL)
	if err != nil || parsed.Host == "" || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || bridgeToken == "" {
		return errors.New("invalid private Watcher bridge configuration")
	}
	bridgeURL = strings.TrimRight(bridgeURL, "/")
	return nil
}
func GetName() string { return "watcher" }
func Cleanup() error  { bridgeClient.CloseIdleConnections(); return nil }
func HTTPTransportPreAuthHook(_ *schemas.BifrostContext, _ *schemas.HTTPRequest) (*schemas.HTTPResponse, error) {
	return nil, nil
}

func consult(endpoint string, request, response json.RawMessage, identity, path, userAgent string) error {
	payload, err := json.Marshal(map[string]any{"request": request, "response": response, "metadata": map[string]string{"watcher_conversation_id": identity, "watcher_url": path, "watcher_provider": "openai", "watcher_user_agent": userAgent}})
	if err != nil {
		return errors.New("invalid exchange")
	}
	req, err := http.NewRequest("POST", bridgeURL+endpoint, bytes.NewReader(payload))
	if err != nil {
		return errors.New("invalid bridge endpoint")
	}
	req.Header.Set("Authorization", "Bearer "+bridgeToken)
	req.Header.Set("Content-Type", "application/json")
	reply, err := bridgeClient.Do(req)
	if err != nil {
		return errors.New("Watcher unavailable; response withheld")
	}
	defer reply.Body.Close()
	body, err := io.ReadAll(io.LimitReader(reply.Body, 4097))
	var verdict struct {
		Verdict *bool `json:"verdict"`
	}
	if err != nil || len(body) > 4096 || reply.StatusCode != 200 || json.Unmarshal(body, &verdict) != nil || verdict.Verdict == nil || !*verdict.Verdict {
		return errors.New("Watcher withheld this response")
	}
	return nil
}

// HTTPTransportPreHook validates the client-facing request before provider calls.
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
	userAgent := ""
	for key, value := range req.Headers {
		if strings.EqualFold(key, "User-Agent") {
			userAgent = value
			break
		}
	}
	if err := consult("/validate", req.Body, nil, identity, req.Path, userAgent); err != nil {
		return nil, err
	}
	// Streaming callbacks outlive the pooled HTTP request body.
	ctx.SetValue(stateKey, &streamState{Request: append(json.RawMessage(nil), req.Body...), Path: req.Path, UserAgent: userAgent, Tools: make(map[int]map[string]any)})
	return nil, nil
}

// HTTPTransportPostHook checks the exact complete body before buffered delivery.
func HTTPTransportPostHook(ctx *schemas.BifrostContext, req *schemas.HTTPRequest, resp *schemas.HTTPResponse) error {
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
	state, ok := ctx.Value(stateKey).(*streamState)
	if !ok || state == nil {
		withholdResponse(resp)
		return nil
	}
	if err := consult("/evaluate", state.Request, resp.Body, identity, state.Path, state.UserAgent); err != nil {
		withholdResponse(resp)
	}
	return nil
}

// withholdResponse replaces the deliverable itself: Bifrost logs post-hook errors
// without withholding the body. Empty encoding clears any provider compression
// header when Bifrost copies these headers onto its existing HTTP response.
func withholdResponse(resp *schemas.HTTPResponse) {
	resp.StatusCode = http.StatusForbidden
	resp.Body = []byte(`{"error":"Watcher withheld this response"}`)
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
	Text, Refusal   string
	Tools           map[int]map[string]any
	Bytes           int
	Done            bool
}

// HTTPTransportStreamChunkHook suppresses original chunks and releases one newly
// encoded, evaluated completion delta when the provider's finish marker arrives.
// A missing marker, oversized stream or unsupported content releases no tools.
func HTTPTransportStreamChunkHook(ctx *schemas.BifrostContext, req *schemas.HTTPRequest, chunk *schemas.BifrostStreamChunk) (*schemas.BifrostStreamChunk, error) {
	state, ok := ctx.Value(stateKey).(*streamState)
	if !ok || chunk.BifrostChatResponse == nil || chunk.BifrostError != nil {
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
	if err = consult("/evaluate", state.Request, body, identity, state.Path, state.UserAgent); err != nil {
		return nil, err
	}
	// Re-encode solely from the message evaluated by Watcher, never replay held bytes.
	if calls, ok := message["tool_calls"].([]any); ok {
		for i, item := range calls {
			item.(map[string]any)["index"] = i
		}
	}
	response["object"] = "chat.completion.chunk"
	response["choices"] = []any{map[string]any{"index": 0, "delta": message, "finish_reason": finish}}
	body, err = json.Marshal(response)
	if err != nil {
		return nil, err
	}
	var result schemas.BifrostChatResponse
	if err = json.Unmarshal(body, &result); err != nil {
		return nil, err
	}
	state.Done = true
	return &schemas.BifrostStreamChunk{BifrostChatResponse: &result}, nil
}
