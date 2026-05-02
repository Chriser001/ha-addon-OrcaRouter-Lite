// Vercel AI SDK + OrcaRouter Lite
//
//   npm install ai @ai-sdk/openai
//
// The @ai-sdk/openai provider lets you point at any OpenAI-compatible base URL.
// Lite serves the OpenAI Chat Completions protocol, so this works as a drop-in.

import { createOpenAI } from "@ai-sdk/openai";
import { generateText, streamText } from "ai";

export const orca = createOpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: process.env.ORCA_API_KEY!, // sk-orca-...
});

// model="auto" → cheapest capable model per request
export async function ask(prompt: string) {
  const { text } = await generateText({
    model: orca("auto"),
    prompt,
  });
  return text;
}

// Streaming
export async function ask_stream(prompt: string) {
  const { textStream } = await streamText({
    model: orca("auto"),
    prompt,
  });
  for await (const chunk of textStream) process.stdout.write(chunk);
}

// Pin a specific model
export const haiku = orca("claude-3-5-haiku-latest");
export const sonnet = orca("claude-3-5-sonnet-latest");
export const gpt4o = orca("gpt-4o");
