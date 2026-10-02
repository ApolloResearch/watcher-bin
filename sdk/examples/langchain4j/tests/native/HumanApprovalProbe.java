import com.example.watcher.examples.langchain4j.WatcherMonitoredExample;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;

/** Local test driver: a test-provided file stands in for the application's human UI. */
public final class HumanApprovalProbe {
    public static void main(String[] args) throws Exception {
        WatcherMonitoredExample.run(args, (request, history) -> {
            try {
                var directory = Path.of(args[2]);
                Files.writeString(directory.resolve("approval-entered.txt"), request.id());
                var answer = directory.resolve("human-choice.txt");
                var deadline = Instant.now().plusSeconds(30);
                while (!Files.exists(answer)) {
                    if (Instant.now().isAfter(deadline)) throw new IllegalStateException("Fixture approval timed out");
                    Thread.sleep(20);
                }
                return Files.readString(answer).equals("allow");
            } catch (Exception error) { throw new IllegalStateException(error); }
        });
    }
}
