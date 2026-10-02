package com.example.watcher.examples.langchain4j;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import dev.langchain4j.agent.tool.ToolSpecification;
import dev.langchain4j.data.message.*;
import dev.langchain4j.model.chat.listener.ChatModelListener;
import dev.langchain4j.model.chat.listener.ChatModelResponseContext;
import dev.langchain4j.model.chat.request.json.JsonObjectSchema;
import dev.langchain4j.model.openai.OpenAiChatModel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import dev.langchain4j.service.AiServices;
import dev.langchain4j.service.tool.ToolExecutor;

/** Capture native LangChain4j response-listener history as Inspect chat dictionaries.
 * The Python bridge submits these snapshots after the run; this cannot deny tools.
 */
public final class WatcherExample {
    private static final ObjectMapper JSON = new ObjectMapper(JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build());

    /** Translate only readable text and client tools; fail on unsupported message kinds. */
    public static List<Map<String, Object>> transcript(List<ChatMessage> history) throws Exception {
        var result = new ArrayList<Map<String, Object>>();
        var ids = new HashSet<String>();
        for (var message : history) {
            var row = new LinkedHashMap<String, Object>();
            if (message instanceof SystemMessage system) {
                row.put("role", "system"); row.put("content", system.text());
            } else if (message instanceof UserMessage user) {
                if (user.contents().stream().anyMatch(content -> !(content instanceof TextContent))) {
                    throw new IllegalArgumentException("Unsupported user content");
                }
                row.put("role", "user"); row.put("content", user.singleText());
            } else if (message instanceof AiMessage assistant) {
                row.put("role", "assistant"); row.put("content", assistant.text() == null ? "" : assistant.text());
                if (assistant.hasToolExecutionRequests()) {
                    var calls = new ArrayList<Map<String, Object>>();
                    for (var call : assistant.toolExecutionRequests()) {
                        if (call.id() == null || !ids.add(call.id())) throw new IllegalArgumentException("Missing or duplicate call ID");
                        var arguments = JSON.readTree(call.arguments());
                        if (!arguments.isObject()) throw new IllegalArgumentException("Tool arguments must be an object");
                        calls.add(Map.of("id", call.id(), "function", call.name(), "arguments", arguments, "type", "function"));
                    }
                    row.put("tool_calls", calls);
                }
            } else if (message instanceof ToolExecutionResultMessage tool) {
                if (!ids.contains(tool.id())) throw new IllegalArgumentException("Unmatched tool result");
                row.put("role", "tool"); row.put("tool_call_id", tool.id()); row.put("content", tool.text());
            } else throw new IllegalArgumentException("Unsupported message type");
            result.add(row);
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("Expected provider base URL and snapshot directory");
        var snapshots = new ArrayList<List<Map<String, Object>>>();
        var failures = new ArrayList<String>();
        var listener = new ChatModelListener() {
            @Override public void onResponse(ChatModelResponseContext context) {
                var history = new ArrayList<>(context.chatRequest().messages());
                history.add(context.chatResponse().aiMessage());
                try { snapshots.add(transcript(history)); }
                catch (Exception failure) { failures.add(failure.getClass().getSimpleName()); }
            }
        };
        String apiKey = System.getenv("PROVIDER_API_KEY");
        var model = OpenAiChatModel.builder().baseUrl(args[0]).apiKey(apiKey == null ? "fixture-key" : apiKey)
            .modelName(System.getenv().getOrDefault("PROVIDER_MODEL", "fixture-model"))
            .maxRetries(0).timeout(Duration.ofSeconds(10)).listeners(List.of(listener)).build();
        var weather = ToolSpecification.builder().name("weather").description("Get city weather")
            .parameters(JsonObjectSchema.builder().addStringProperty("city").required("city").build()).build();
        ToolExecutor tool = (request, memoryId) -> "fixture weather result";
        var assistant = AiServices.builder(WatcherMonitoredExample.Assistant.class).chatModel(model)
            .tools(Map.of(weather, tool)).maxToolCallingRoundTrips(4).build();
        assistant.chat("Call weather for Paris and Tokyo, then summarize.");
        if (!failures.isEmpty()) throw new IllegalStateException(String.join(", ", failures));
        Files.createDirectories(Path.of(args[1]));
        for (int i = 0; i < snapshots.size(); i++) {
            JSON.writeValue(Path.of(args[1], i + ".json").toFile(), snapshots.get(i));
        }
    }
}
