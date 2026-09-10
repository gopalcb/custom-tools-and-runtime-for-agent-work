import { Injectable, Logger } from '@nestjs/common';
import { appendFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { ApplicationLogLevel, RuntimeLogRequest } from './contracts';

const LOG_LEVELS = new Set<ApplicationLogLevel>(['DEBUG', 'INFO', 'WARN', 'ERROR']);
const DEFAULT_SOURCE = 'monorepo-controller/backend-api-services';
const MAX_FIELD_LENGTH = 12000;

@Injectable()
export class ApplicationLogService {
  private readonly logger = new Logger(ApplicationLogService.name);
  private readonly logDirectory = process.env.SYS_LOG_DIR
    ? resolve(process.env.SYS_LOG_DIR)
    : resolve(__dirname, '..', '..', 'sys-logs');

  async writeLog(payload: unknown, defaultSource = DEFAULT_SOURCE): Promise<void> {
    const entry = this.record(payload);
    const now = this.timestamp(entry.timestamp);
    const level = this.level(entry.level);
    const source = this.text(entry.source) || defaultSource;
    const message = this.message(entry);
    const line = `${now.toISOString()} - ${source} - ${level} - ${message}\n`;

    try {
      await mkdir(this.logDirectory, { recursive: true });
      await appendFile(`${this.logDirectory}/${this.fileName(now)}`, line, 'utf8');
    } catch (error) {
      this.logger.error(`Unable to write application log: ${this.errorMessage(error)}`);
    }
  }

  async writeBackendLog(level: ApplicationLogLevel, message: string, source: string, details?: unknown): Promise<void> {
    await this.writeLog({ level, message, source, details }, source);
  }

  private record(payload: unknown): RuntimeLogRequest {
    if (payload && typeof payload === 'object' && !Array.isArray(payload)) return payload as RuntimeLogRequest;
    return { level: 'ERROR', message: 'Invalid application log payload', details: payload };
  }

  private timestamp(value: unknown): Date {
    if (typeof value !== 'string' || !value.trim()) return new Date();
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
  }

  private level(value: unknown): ApplicationLogLevel {
    const normalized = typeof value === 'string' ? value.toUpperCase() : 'INFO';
    return LOG_LEVELS.has(normalized as ApplicationLogLevel) ? normalized as ApplicationLogLevel : 'INFO';
  }

  private message(entry: RuntimeLogRequest): string {
    const message = this.text(entry.message) || 'Application runtime log';
    const metadata: Record<string, unknown> = {};
    if (entry.url) metadata.url = entry.url;
    if (entry.userAgent) metadata.userAgent = entry.userAgent;
    if (entry.details !== undefined) metadata.details = entry.details;
    if (!Object.keys(metadata).length) return message;

    try {
      return this.limit(`${message} ${JSON.stringify(metadata)}`);
    } catch {
      return this.limit(`${message} ${String(metadata)}`);
    }
  }

  private fileName(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `log-${year}-${month}-${day}.log`;
  }

  private text(value: unknown): string {
    if (typeof value !== 'string') return '';
    return this.limit(value.replace(/\s+/g, ' ').trim());
  }

  private limit(value: string): string {
    return value.length > MAX_FIELD_LENGTH ? `${value.slice(0, MAX_FIELD_LENGTH)}...` : value;
  }

  private errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }
}
