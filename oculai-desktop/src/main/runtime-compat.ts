// Runtime compatibility shims for Electron's bundled Node version.
// Some Pi SDK dependencies load a recent undici build that expects
// worker_threads.markAsUncloneable, which is unavailable in Electron 31's Node.
import { createRequire } from "module";
import Module from "module";

const require = createRequire(import.meta.url);
const noopMarkAsUncloneable = () => {};

function withWorkerThreadCompat(exportsValue: unknown) {
  if (exportsValue && typeof exportsValue === "object") {
    const target = exportsValue as { markAsUncloneable?: (value: unknown) => void };
    if (typeof target.markAsUncloneable !== "function") {
      try {
        target.markAsUncloneable = noopMarkAsUncloneable;
        return target;
      } catch {
        return { ...target, markAsUncloneable: noopMarkAsUncloneable };
      }
    }
  }
  return exportsValue;
}

withWorkerThreadCompat(require("node:worker_threads"));

const moduleWithLoad = Module as unknown as {
  _load?: (request: string, parent: unknown, isMain: boolean) => unknown;
  __oculaiWorkerThreadsCompatPatched?: boolean;
};

if (moduleWithLoad._load && !moduleWithLoad.__oculaiWorkerThreadsCompatPatched) {
  const originalLoad = moduleWithLoad._load;
  moduleWithLoad._load = function patchedLoad(request: string, parent: unknown, isMain: boolean) {
    const loaded = originalLoad.call(this, request, parent, isMain);
    if (request === "node:worker_threads" || request === "worker_threads") {
      return withWorkerThreadCompat(loaded);
    }
    return loaded;
  };
  moduleWithLoad.__oculaiWorkerThreadsCompatPatched = true;
}
