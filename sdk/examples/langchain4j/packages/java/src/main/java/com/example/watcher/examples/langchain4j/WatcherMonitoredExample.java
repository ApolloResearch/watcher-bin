package com.example.watcher.examples.langchain4j;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.agent.tool.ToolExecutionRequest;
import dev.langchain4j.agent.tool.ToolSpecification;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.memory.ChatMemory;
import dev.langchain4j.memory.chat.MessageWindowChatMemory;
import dev.langchain4j.model.chat.request.json.JsonObjectSchema;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.service.AiServices;
import dev.langchain4j.service.tool.BeforeToolExecution;
import dev.langchain4j.service.tool.ToolExecutor;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.*;
import java.util.function.Consumer;

/** Native AiServices tool execution with a public Python SDK permission bridge. */
public final class WatcherMonitoredExample {
    private static final ObjectMapper JSON = new ObjectMapper();

    public interface Assistant { String chat(String message); }

    /** Obtain an authorized human choice while the native call remains pending.
     * Implementations must not change arguments or automatically approve by a model.
     * The SDK bridge records the choice and verifies it before an approval releases execution.
     */
    @FunctionalInterface
    public interface HumanApproval {
        boolean approve(ToolExecutionRequest request, List<ChatMessage> history);
    }

    /** Register one instance with AiServices.beforeToolExecution for one conversation.
     * The callback checks original native IDs against the same ChatMemory used by
     * AiServices. Failed IDs cannot be retried. Transport failures and denials
     * withhold execution; only a configured human callback can resolve escalation.
     * Observe and paused settings preserve the native dispatch behavior.
     */
    public static final class Guard implements Consumer<BeforeToolExecution> {
        private final Set<String> attempted = new HashSet<>();
        private final String python;
        private final ChatMemory memory;
        private final HumanApproval humanApproval;

        public Guard(String python, ChatMemory memory, HumanApproval humanApproval) {
            this.python = Objects.requireNonNull(python, "WATCHER_PYTHON is required");
            this.memory = Objects.requireNonNull(memory);
            this.humanApproval = humanApproval;
        }

        private int submit(List<ChatMessage> history, String callId, String humanDecision) throws Exception {
            var command = new ArrayList<>(List.of(python, "-m", "watcher_langchain4j_bridge.gate"));
            if (humanDecision != null) command.addAll(List.of("--human-decision", humanDecision));
            if (callId != null) command.addAll(List.of("--", callId));
            var process = new ProcessBuilder(command).redirectError(ProcessBuilder.Redirect.INHERIT)
                .redirectOutput(ProcessBuilder.Redirect.DISCARD).start();
            try (var input = process.getOutputStream()) {
                JSON.writeValue(input, WatcherExample.transcript(history));
            }
            return process.waitFor();
        }

        @Override public synchronized void accept(BeforeToolExecution event) {
            var call = event.request();
            if (call.id() == null || !attempted.add(call.id())) {
                throw new IllegalArgumentException("Missing or repeated native identity");
            }
            var history = List.copyOf(memory.messages());
            try {
                var status = submit(history, call.id(), null);
                if (status == 0) return;
                if (status == 3 && humanApproval != null) {
                    boolean approved = humanApproval.approve(call, history);
                    if (submit(history, call.id(), approved ? "allow" : "deny") != 0) {
                        throw new IllegalStateException("Human decision reporting failed");
                    }
                    if (approved) return;
                }
                throw new IllegalStateException("Watcher withheld execution");
            } catch (RuntimeException error) {
                throw error;
            } catch (Exception error) {
                throw new IllegalStateException("Watcher permission request failed", error);
            }
        }

        /** Submit retained native results and the final model answer after chat returns. */
        public void record() throws Exception {
            if (submit(memory.messages(), null, null) != 0) throw new IllegalStateException("Transcript submission failed");
        }
    }

    /** Run a native AiServices conversation; the tool writes an observable local file. */
    public static void main(String[] args) throws Exception { run(args, null); }

    /** The application supplies an optional human approval UI; null means unattended. */
    public static void run(String[] args, HumanApproval approval) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("Expected provider URL, effect file, snapshot directory");
        var model = OpenAiChatModel.builder().baseUrl(args[0])
            .apiKey(System.getenv().getOrDefault("PROVIDER_API_KEY", "fixture-key"))
            .modelName(System.getenv().getOrDefault("PROVIDER_MODEL", "fixture-model"))
            .maxRetries(0).timeout(Duration.ofSeconds(10)).build();
        var weather = ToolSpecification.builder().name("weather").description("Get city weather")
            .parameters(JsonObjectSchema.builder().addStringProperty("city").required("city").build()).build();
        var memory = MessageWindowChatMemory.withMaxMessages(1000);
        var guard = new Guard(System.getenv("WATCHER_PYTHON"), memory, approval);
        ToolExecutor tool = (request, memoryId) -> {
            try {
                var city = JSON.readTree(request.arguments()).get("city").asText();
                Files.writeString(Path.of(args[1]), city + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND);
                return "fixture weather result";
            } catch (Exception error) { throw new IllegalStateException("Tool failed", error); }
        };
        var assistant = AiServices.builder(Assistant.class).chatModel(model).chatMemory(memory)
            .tools(Map.of(weather, tool)).beforeToolExecution(guard).maxToolCallingRoundTrips(4).build();
        assistant.chat("Call weather for Paris and Tokyo, then summarize.");
        guard.record();
        Files.createDirectories(Path.of(args[2]));
        JSON.writeValue(Path.of(args[2], "final.json").toFile(), WatcherExample.transcript(memory.messages()));
    }
}
