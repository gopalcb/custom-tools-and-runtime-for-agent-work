import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { ApplicationLogService } from './application-log.service';
import { AppModule } from './app.module';

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create(AppModule);
  app.enableCors({ origin: process.env['UI_ORIGIN']?.split(',') ?? true, credentials: true });
  const port = Number(process.env.PORT ?? 1002);
  const host = process.env.HOST ?? 'localhost';
  await app.listen(port, host);
  const applicationLogs = app.get(ApplicationLogService);
  await applicationLogs.writeBackendLog('INFO', `Backend API listening on ${host}:${port}.`, 'monorepo-controller/backend-api-services/src/main.ts');
}

void bootstrap().catch(async (error: unknown) => {
  const applicationLogs = new ApplicationLogService();
  await applicationLogs.writeBackendLog(
    'ERROR',
    'Backend API failed to start.',
    'monorepo-controller/backend-api-services/src/main.ts',
    { error: error instanceof Error ? error.stack ?? error.message : String(error) },
  );
  process.exitCode = 1;
});
