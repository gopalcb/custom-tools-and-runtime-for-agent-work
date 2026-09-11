import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

export function findProjectRoot(start: string = process.cwd()): string {
  const configured = process.env['MONOREPO_ROOT'];
  if (configured) return resolve(configured);
  let current = resolve(start);
  while (true) {
    if (existsSync(resolve(current, 'project-registry.yaml')) && existsSync(resolve(current, 'agent-config', 'agents'))) {
      return current;
    }
    const parent = resolve(current, '..');
    if (parent === current) break;
    current = parent;
  }
  throw new Error('Unable to locate monorepo project root.');
}

export function safeJoin(root: string, ...segments: string[]): string {
  const target = resolve(root, ...segments);
  if (target !== root && !target.startsWith(`${root}/`)) {
    throw new Error(`Path escapes monorepo root: ${target}`);
  }
  return target;
}

export function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  return {};
}

export function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}
