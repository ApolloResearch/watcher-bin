/** Python startup must be a fail-closed boundary before Mastra executes a tool. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { submit } from 'watcher-mastra-example/monitoring';

test('missing Python configuration refuses authorization', async () => {
  const previous = process.env.WATCHER_PYTHON;
  delete process.env.WATCHER_PYTHON;
  try {
    await assert.rejects(submit([], 'call-a'), /WATCHER_PYTHON is required/);
  } finally {
    if (previous === undefined) delete process.env.WATCHER_PYTHON;
    else process.env.WATCHER_PYTHON = previous;
  }
});

test('a missing Python executable refuses authorization', async () => {
  const previous = process.env.WATCHER_PYTHON;
  process.env.WATCHER_PYTHON = '/missing-watcher-python-executable';
  try {
    await assert.rejects(submit([], 'call-a'), /ENOENT/);
  } finally {
    if (previous === undefined) delete process.env.WATCHER_PYTHON;
    else process.env.WATCHER_PYTHON = previous;
  }
});
