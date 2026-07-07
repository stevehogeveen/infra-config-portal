import { build } from "esbuild";
import { existsSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";

const root = process.cwd();
const outDir = path.join(root, "node_modules/.cache/component-tests");
const tests = findTests(path.join(root, "src"));

if (!tests.length) {
  console.log("No component tests found.");
  process.exit(0);
}

rmSync(outDir, { force: true, recursive: true });
mkdirSync(outDir, { recursive: true });

let passed = 0;
for (const testFile of tests) {
  const outfile = path.join(outDir, `${path.basename(testFile).replace(/\W+/g, "_")}.mjs`);
  await build({
    bundle: true,
    entryPoints: [testFile],
    external: ["react", "react-dom/server", "react/jsx-runtime", "react-router-dom", "lucide-react"],
    format: "esm",
    jsx: "automatic",
    logLevel: "silent",
    outfile,
    platform: "node",
    sourcemap: "inline"
  });

  const module = await import(pathToFileURL(outfile).href);
  if (typeof module.run !== "function") {
    throw new Error(`${path.relative(root, testFile)} must export run()`);
  }
  await module.run();
  passed += 1;
  console.log(`ok ${passed} ${path.relative(root, testFile)}`);
}

if (!existsSync(outDir)) {
  throw new Error("component test cache was unexpectedly removed");
}
console.log(`${passed} component test file(s) passed.`);

function findTests(dir) {
  if (!existsSync(dir)) {
    return [];
  }
  const result = [];
  for (const entry of readdirSync(dir)) {
    const fullPath = path.join(dir, entry);
    const stats = statSync(fullPath);
    if (stats.isDirectory()) {
      result.push(...findTests(fullPath));
    } else if (entry.endsWith(".component.test.tsx")) {
      result.push(fullPath);
    }
  }
  return result.sort();
}
