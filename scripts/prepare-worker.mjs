import { cp, mkdir, rm } from "node:fs/promises";
import { join } from "node:path";

const root = process.cwd();
const output = join(root, "dist");

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });

await cp(join(root, "worker.py"), join(output, "worker.py"));
await cp(join(root, "backend"), join(output, "backend"), {
  recursive: true,
  filter: (source) => !source.includes("__pycache__"),
});
