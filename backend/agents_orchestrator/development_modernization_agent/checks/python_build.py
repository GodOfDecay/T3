"""The Python toolchain's BUILD — runs INSIDE the sandbox (python image, standard library only).

    python /sdlc/python_build.py <module path>

Python has no compile step that catches a port's real breakages: `import urllib2` is valid syntax on
Python 3 and fails only when the code runs. So a build here is two checks, without executing the
module's own code:
  1. every .py file compiles on this runtime (syntax);
  2. every absolute import resolves on this runtime, or to a file of the module itself.
A third-party package the module needs and the image does not have is reported too: it must be
declared and provided (the organisation's package mirror), never silently assumed.
"""
import ast
import importlib.util
import pathlib
import sys


def main(path):
    root = pathlib.Path(path)
    if not root.is_dir():
        print("%s is not a folder" % path)
        return 2
    sys.path.insert(0, str(root))
    errors, files = [], sorted(root.rglob("*.py"))
    for f in files:
        source = f.read_text(encoding="utf-8", errors="replace")
        try:
            tree = compile(source, str(f), "exec", ast.PyCF_ONLY_AST, dont_inherit=True)
            compile(tree, str(f), "exec", dont_inherit=True)
        except SyntaxError as e:
            errors.append("%s:%s: SyntaxError: %s" % (f, e.lineno, e.msg))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                try:
                    found = importlib.util.find_spec(name) is not None
                except (ImportError, ValueError):
                    found = False
                if not found:
                    errors.append("%s:%s: cannot import %s on this runtime" % (f, node.lineno, name))
    print("\n".join(errors) if errors else "%d file(s) compile and every import resolves" % len(files))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
