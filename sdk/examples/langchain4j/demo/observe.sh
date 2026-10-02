#!/bin/sh
: "${WATCHER_JAVA_CLASSPATH:?Set the installed JAR and dependency classpath}"
exec "${JAVA_BIN:-java}" -cp "$WATCHER_JAVA_CLASSPATH" com.example.watcher.examples.langchain4j.WatcherExample "$@"
