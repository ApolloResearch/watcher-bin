/** Observe Mastra's native completed-step messages using standard Inspect chat dictionaries. */
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

export function transcript(messages) {
  const result = [];
  const ids = new Set();
  const pending = new Map();
  for (const message of messages) {
    if (!['system', 'user', 'assistant', 'tool'].includes(message.role)) throw new Error('Unsupported role');
    if (typeof message.content === 'string') {
      if (message.role === 'tool') throw new Error('Tool messages require linked tool results');
      result.push({role: message.role, content: message.content});
      continue;
    }
    const mapped = {role: message.role, content: []};
    for (const part of message.content) {
      if (message.role === 'tool' && part.type !== 'tool-result') {
        throw new Error('Tool messages require linked tool results');
      }
      if (part.type === 'text') mapped.content.push({type: 'text', text: part.text});
      else if (part.type === 'reasoning') mapped.content.push({type: 'reasoning', reasoning: part.text});
      else if (part.type === 'tool-call') {
        if (message.role !== 'assistant' || typeof part.toolCallId !== 'string' || !part.toolCallId ||
            ids.has(part.toolCallId) || typeof part.toolName !== 'string' || !part.toolName ||
            part.input === null || typeof part.input !== 'object' || Array.isArray(part.input)) {
          throw new Error('Malformed tool call');
        }
        ids.add(part.toolCallId);
        pending.set(part.toolCallId, part.toolName);
        (mapped.tool_calls ??= []).push({id: part.toolCallId, function: part.toolName,
          arguments: structuredClone(part.input), type: 'function'});
      } else if (part.type === 'tool-result') {
        if (message.role !== 'tool' || !pending.has(part.toolCallId) || pending.get(part.toolCallId) !== part.toolName) {
          throw new Error('Unmatched tool result');
        }
        if (!['text', 'json', 'error-text', 'error-json'].includes(part.output.type)) throw new Error('Unsupported tool output');
        const toolResult = {role: 'tool', tool_call_id: part.toolCallId,
          content: typeof part.output.value === 'string' ? part.output.value : JSON.stringify(part.output.value)};
        if (part.output.type === 'error-text' || part.output.type === 'error-json') {
          toolResult.error = {type: 'unknown', message: 'Tool reported an error'};
        }
        result.push(toolResult);
        pending.delete(part.toolCallId);
      } else throw new Error('Unsupported content');
    }
    if (mapped.content.length || mapped.tool_calls) result.push(mapped);
  }
  return result;
}

/** Run a real Mastra agent, writing complete snapshots after each native step.
 * Tool execution has already happened at this seam. This is observation, never enforcement.
 * sink receives only Inspect-compatible messages; no framework-specific envelope is invented.
 */
export async function run(model, sink, executeWeather = async ({city}) => ({city, weather: 'fixture'})) {
  const instructions = 'Call weather once for Paris and once for Tokyo, then summarize.';
  const agent = new Agent({id: 'watcher-example', name: 'Watcher example', instructions, model,
    tools: {weather: createTool({id: 'weather', description: 'Return the weather for a city',
      inputSchema: z.object({city: z.string()}), execute: executeWeather})}});
  const prompt = 'Paris and Tokyo?';
  const result = await agent.generate(prompt, {maxSteps: 3,
    onStepFinish: async step => {
      if (!step.response.messages.length) return;
      await sink(transcript([{role: 'system', content: instructions}, {role: 'user', content: prompt},
        ...step.response.messages]));
    }});
  return result;
}
