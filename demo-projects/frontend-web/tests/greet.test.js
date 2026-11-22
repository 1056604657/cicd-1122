import { test } from 'node:test';
import assert from 'node:assert/strict';
import { greet } from '../src/app.js';

test('greet returns name when provided', () => {
  assert.equal(greet('GitLab'), 'Hello, GitLab');
});

test('greet falls back to world when blank', () => {
  assert.equal(greet('   '), 'Hello, world');
});
