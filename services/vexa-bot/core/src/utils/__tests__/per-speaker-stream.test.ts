/**
 * Unit tests for per-speaker audio stream selection.
 *
 * Run: cd core && npx tsx src/utils/__tests__/per-speaker-stream.test.ts
 *
 * Regression guard for the four-month silent outage: the per-speaker graph
 * bound to document.querySelector('audio') while the recorder used its own
 * combined stream. When that one element went silent the bot still recorded
 * complete audio and produced zero transcript segments.
 */

import assert from 'node:assert';
import { selectPerSpeakerAudioStream } from '../browser';

let passed = 0;
let failed = 0;

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (err: any) {
    console.log(`  FAIL  ${name}`);
    console.log(`        ${err.message}`);
    failed++;
  }
}

function fakeStream(trackCount: number, label = 'stream') {
  return {
    label,
    getAudioTracks: () => new Array(trackCount).fill({ kind: 'audio' }),
  };
}

function fakeDoc(audioElement: any) {
  return { querySelector: (sel: string) => (sel === 'audio' ? audioElement : null) };
}

console.log('\nper-speaker stream selection\n');

test('prefers the combined recorder stream over the audio element', () => {
  const combined = fakeStream(2, 'combined');
  const element = fakeStream(1, 'element');
  const result = selectPerSpeakerAudioStream(
    { __vexaCombinedAudioStream: combined },
    fakeDoc({ srcObject: element })
  );
  assert.ok(result, 'expected a selection');
  assert.strictEqual(result!.origin, 'combined');
  assert.strictEqual((result!.stream as any).label, 'combined');
});

test('takes the combined stream even when no audio element exists at all', () => {
  const combined = fakeStream(1, 'combined');
  const result = selectPerSpeakerAudioStream(
    { __vexaCombinedAudioStream: combined },
    fakeDoc(null)
  );
  assert.ok(result);
  assert.strictEqual(result!.origin, 'combined');
});

test('falls back to the audio element when the combined stream is missing', () => {
  const element = fakeStream(1, 'element');
  const result = selectPerSpeakerAudioStream({}, fakeDoc({ srcObject: element }));
  assert.ok(result);
  assert.strictEqual(result!.origin, 'audio-element-fallback');
  assert.strictEqual((result!.stream as any).label, 'element');
});

test('falls back when the combined stream carries no audio tracks', () => {
  const element = fakeStream(1, 'element');
  const result = selectPerSpeakerAudioStream(
    { __vexaCombinedAudioStream: fakeStream(0, 'combined') },
    fakeDoc({ srcObject: element })
  );
  assert.ok(result);
  assert.strictEqual(result!.origin, 'audio-element-fallback');
});

test('returns null when neither source has audio tracks', () => {
  const result = selectPerSpeakerAudioStream(
    { __vexaCombinedAudioStream: fakeStream(0) },
    fakeDoc({ srcObject: fakeStream(0) })
  );
  assert.strictEqual(result, null);
});

test('returns null when the audio element has no MediaStream srcObject', () => {
  const result = selectPerSpeakerAudioStream({}, fakeDoc({ srcObject: null }));
  assert.strictEqual(result, null);
});

test('survives a missing window and document', () => {
  assert.strictEqual(selectPerSpeakerAudioStream(undefined, undefined), null);
});

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
