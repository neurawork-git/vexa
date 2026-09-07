/**
 * Unit tests for TranscriptionClient request shape and response parsing.
 *
 * Run: cd core && npx tsx src/services/__tests__/transcription-client.test.ts
 *
 * Backed by a local HTTP stub — no network, no Docker. Guards the Azure
 * transcribe path: gpt-4o(-mini)-transcribe reject `verbose_json` and the VAD
 * tuning fields with HTTP 400, and answer with full text and no `segments`
 * array. The client must be able to speak that dialect without a rebuild, and
 * must still return usable text when segments are absent.
 */

import assert from 'node:assert';
import http from 'node:http';
import { AddressInfo } from 'node:net';
import { TranscriptionClient } from '../transcription-client';

let passed = 0;
let failed = 0;

async function test(name: string, fn: () => Promise<void>) {
  try {
    await fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (err: any) {
    console.log(`  FAIL  ${name}`);
    console.log(`        ${err.message}`);
    failed++;
  }
}

/** Captures the raw multipart body of one request and replies with `body`. */
function startStub(body: any): Promise<{ url: string; lastBody: () => string; close: () => void }> {
  let lastBody = '';
  const server = http.createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      lastBody = Buffer.concat(chunks).toString('latin1');
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(body));
    });
  });
  return new Promise(resolve => {
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address() as AddressInfo;
      resolve({
        url: `http://127.0.0.1:${port}/v1/audio/transcriptions`,
        lastBody: () => lastBody,
        close: () => server.close(),
      });
    });
  });
}

function samples(n = 1600): Float32Array {
  const a = new Float32Array(n);
  for (let i = 0; i < n; i++) a[i] = Math.sin(i / 10) * 0.5;
  return a;
}

/** Reads one multipart field value out of the captured body. */
function field(body: string, name: string): string | null {
  const m = body.match(new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]*)\\r\\n`));
  return m ? m[1] : null;
}

(async () => {
  console.log('\ntranscription client request shape\n');

  await test('defaults keep the whisper-compatible shape', async () => {
    const stub = await startStub({ text: 'hallo', segments: [] });
    const client = new TranscriptionClient({
      serviceUrl: stub.url,
      maxSpeechDurationSec: 15,
      minSilenceDurationMs: 100,
    });
    await client.transcribe(samples(), 'de');
    const body = stub.lastBody();
    stub.close();
    assert.strictEqual(field(body, 'model'), 'whisper-1');
    assert.strictEqual(field(body, 'response_format'), 'verbose_json');
    assert.strictEqual(field(body, 'timestamp_granularities'), 'word');
    assert.strictEqual(field(body, 'max_speech_duration_s'), '15');
    assert.strictEqual(field(body, 'min_silence_duration_ms'), '100');
  });

  await test('azure transcribe shape drops every field the model rejects', async () => {
    const stub = await startStub({ text: 'hallo' });
    const client = new TranscriptionClient({
      serviceUrl: stub.url,
      responseFormat: 'json',
      wordTimestamps: false,
      sendVadTuning: false,
      maxSpeechDurationSec: 15,
      minSilenceDurationMs: 100,
    });
    await client.transcribe(samples(), 'de');
    const body = stub.lastBody();
    stub.close();
    assert.strictEqual(field(body, 'response_format'), 'json');
    assert.strictEqual(field(body, 'timestamp_granularities'), null, 'word timestamps must be absent');
    assert.strictEqual(field(body, 'max_speech_duration_s'), null, 'VAD tuning must be absent');
    assert.strictEqual(field(body, 'min_silence_duration_ms'), null, 'VAD tuning must be absent');
    assert.strictEqual(field(body, 'language'), 'de', 'language still applies');
  });

  await test('model name is configurable', async () => {
    const stub = await startStub({ text: 'hallo' });
    const client = new TranscriptionClient({ serviceUrl: stub.url, model: 'gpt-4o-mini-transcribe' });
    await client.transcribe(samples());
    const body = stub.lastBody();
    stub.close();
    assert.strictEqual(field(body, 'model'), 'gpt-4o-mini-transcribe');
  });

  await test('a response without segments still yields full text', async () => {
    // Exactly what Azure gpt-4o-mini-transcribe returns for response_format=json.
    const stub = await startStub({
      text: 'BSTA steht für Bestandsabgleich.',
      usage: { type: 'tokens', total_tokens: 138 },
    });
    const client = new TranscriptionClient({ serviceUrl: stub.url, responseFormat: 'json' });
    const result = await client.transcribe(samples(), 'de');
    stub.close();
    assert.strictEqual(result.text, 'BSTA steht für Bestandsabgleich.');
    assert.deepStrictEqual(result.segments, [], 'no segments is a valid answer, not a failure');
    assert.strictEqual(result.language, 'de', 'falls back to the requested language');
  });

  await test('segments are still parsed when the backend returns them', async () => {
    const stub = await startStub({
      text: 'eins zwei',
      language: 'de',
      duration: 2,
      segments: [{ start: 0, end: 1, text: 'eins' }, { start: 1, end: 2, text: 'zwei' }],
    });
    const client = new TranscriptionClient({ serviceUrl: stub.url });
    const result = await client.transcribe(samples(), 'de');
    stub.close();
    assert.strictEqual(result.segments.length, 2);
    assert.strictEqual(result.segments[1].text, 'zwei');
    assert.strictEqual(result.duration, 2);
  });

  console.log(`\n=== Results: ${passed} passed, ${failed} failed ===\n`);
  process.exit(failed > 0 ? 1 : 0);
})();
