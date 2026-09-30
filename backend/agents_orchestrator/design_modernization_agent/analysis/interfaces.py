"""What the legacy system exposes and consumes — read from the code, deterministically.

WHY THIS EXISTS (research §6.3). The frozen contracts (CT-xx) are the interfaces other systems
depend on, and a contract the model "remembers" but the code does not show is an invented
consumer. So the inventory is computed, not recalled: every entry is a pattern match with the
file and line it came from, and the record tool checks each contract's location against it.

WHAT IS FOUND, by kind:

  http   exposes: Spring MVC mappings (with the class-level prefix), JAX-RS @Path, web.xml
         servlet mappings, JSP / ASPX pages, ASP.NET attribute routes and minimal APIs, WCF
         service contracts, Flask / FastAPI decorators, Express routes.
         consumes: RestTemplate / WebClient / HttpClient / URL connections, requests / httpx,
         fetch / axios.
  file   writes and reads: Java FileWriter/Files.write…, Python open(..., "w"), .NET File.*,
         Node fs.*.
  job    runs: @Scheduled, Quartz, cron files and expressions, Hangfire / hosted services,
         Python schedulers.
  db     tables: CREATE TABLE in .sql, JPA @Table, EF [Table] / DbSet, and table names in SQL
         string literals and .sql files (FROM / INTO / UPDATE / JOIN).
  queue  consumes / produces: JMS, Kafka, RabbitMQ listeners and templates; IBM MQ in COBOL.
  rpc    exposes: operations DECLARED in contract files — WSDL, gRPC `.proto`, GraphQL schemas
         (OpenAPI/Swagger paths are declared `http`); consumes: CICS LINK/XCTL.
  ui     exposes: mainframe screens (CICS SEND MAP).

Phase F made it universal: also Go (net/http, gin/echo/chi), PHP (Laravel, Symfony), Ruby (Rails,
Sinatra), VB.NET, COBOL and JCL (files assigned, datasets, programs run, embedded SQL), and
Kubernetes CronJobs. A DECLARED contract file is the strongest evidence of all: it is what the
system promises its consumers, whatever the code behind it does.

WHAT IT IS NOT. A pattern scan, not a compiler: it can miss an interface built dynamically,
and it may list a match that is not one. It is evidence for the design, cited by location, and
the design says "proposed" for anything it cannot tie to an entry here. It never reads `.git`,
build output or vendored front-end libraries (the inventory's own rules).
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

from agents_orchestrator.discovery_agent.analysis.inventory import SKIP_DIRS, is_vendored_asset

_MAX_FILE_BYTES = 1_000_000
_MAX_FILES = 20_000
#: The inventory is capped so a huge system cannot flood a tool reply or a page; the cap is
#: reported (`truncated`), never silent.
MAX_ITEMS = 2_000

KINDS = ("http", "rpc", "file", "job", "db", "queue", "ui")


@dataclass(frozen=True)
class Interface:
    kind: str          # http | rpc | file | job | db | queue | ui
    direction: str     # exposes | consumes | writes | reads | runs | defines | uses | produces
    name: str          # the path, file, table, topic or schedule
    location: str      # path:line in the legacy checkout
    module: str = ""   # the module whose directory holds it ("" when none does)
    evidence: str = ""  # the matching line, trimmed

    @property
    def file(self) -> str:
        return self.location.rsplit(":", 1)[0]


# ── patterns ─────────────────────────────────────────────────────────────────

_S = r"""["']([^"']*)["']"""  # a quoted string, captured

_JAVA_CLASS_MAPPING = re.compile(r"@RequestMapping\s*\(\s*(?:(?:value|path)\s*=\s*)?\{?\s*" + _S)
_JAVA_METHOD_MAPPING = re.compile(
    r"@(Get|Post|Put|Delete|Patch|Request)Mapping\b(?:\s*\(\s*(?:(?:value|path)\s*=\s*)?\{?\s*(?:" + _S + r")?)?")
_JAVA_REQUEST_METHOD = re.compile(r"RequestMethod\.(\w+)")
_JAXRS_PATH = re.compile(r"@Path\s*\(\s*" + _S)
_JAXRS_VERB = re.compile(r"@(GET|POST|PUT|DELETE|PATCH)\b")
_CLASS_DECL = re.compile(r"\b(class|interface|enum)\s+\w+")

_URL_LITERAL = re.compile(r"""["'`]((?:https?://|/)[^"'`\s]*)["'`]""")
_QUOTED = re.compile(r"""["'`]([^"'`]+)["'`]""")

_RULES: dict[str, list[tuple[str, str, re.Pattern]]] = {
    # (kind, direction, pattern) — the name is group 1 when the pattern has one.
    "java": [
        ("http", "consumes", re.compile(r"\b(RestTemplate|WebClient|HttpURLConnection|HttpClient|OkHttpClient|"
                                        r"CloseableHttpClient|@FeignClient)\b")),
        ("http", "consumes", re.compile(r"\.(getForObject|getForEntity|postForObject|postForEntity|exchange|"
                                        r"openConnection)\s*\(")),
        ("file", "writes", re.compile(r"new\s+(?:FileWriter|FileOutputStream|PrintWriter|BufferedWriter)\s*\(\s*"
                                      r"(?:new\s+File\s*\(\s*)?([^)]*)")),
        ("file", "writes", re.compile(r"Files\.(?:write|writeString|newBufferedWriter|newOutputStream)\s*\(\s*([^,)]*)")),
        ("file", "reads", re.compile(r"new\s+(?:FileReader|FileInputStream)\s*\(\s*(?:new\s+File\s*\(\s*)?([^)]*)")),
        ("file", "reads", re.compile(r"Files\.(?:readAllLines|readAllBytes|readString|newBufferedReader|lines|"
                                     r"newInputStream)\s*\(\s*([^,)]*)")),
        ("job", "runs", re.compile(r"@Scheduled\s*\(\s*(?:cron\s*=\s*)?" + r"""(?:["']([^"']*)["'])?""")),
        ("job", "runs", re.compile(r"\b(CronScheduleBuilder|CronTrigger|JobBuilder\.newJob|extends\s+QuartzJobBean|"
                                   r"implements\s+(?:org\.quartz\.)?Job\b)")),
        ("db", "defines", re.compile(r"@Table\s*\(\s*name\s*=\s*" + _S)),
        ("queue", "consumes", re.compile(r"@(?:JmsListener|RabbitListener)\s*\(.*?(?:destination|queues)\s*=\s*\{?\s*" + _S)),
        ("queue", "consumes", re.compile(r"@KafkaListener\s*\(.*?topics\s*=\s*\{?\s*" + _S)),
        ("queue", "produces", re.compile(r"(?:kafkaTemplate|jmsTemplate|rabbitTemplate)\.(?:send|convertAndSend)\s*\(\s*" + _S)),
    ],
    "python": [
        ("http", "exposes", re.compile(r"@\w+\.(?:route|get|post|put|delete|patch)\s*\(\s*" + _S)),
        ("http", "consumes", re.compile(r"\b(requests\.(?:get|post|put|delete|patch|request)|httpx\.\w+|"
                                        r"urllib\.request\.urlopen|urllib2\.urlopen|aiohttp\.ClientSession)\b")),
        ("job", "runs", re.compile(r"\b(schedule\.every|BlockingScheduler|BackgroundScheduler|add_job\s*\(|"
                                   r"@periodic_task|crontab\s*\()")),
    ],
    "csharp": [
        ("http", "consumes", re.compile(r"\b(HttpClient|WebRequest\.Create|new\s+WebClient)\b")),
        ("file", "writes", re.compile(r"File\.(?:WriteAll\w+|AppendAll\w+|Create|OpenWrite)\s*\(\s*([^,)]*)")),
        ("file", "writes", re.compile(r"new\s+StreamWriter\s*\(\s*([^,)]*)")),
        ("file", "reads", re.compile(r"File\.(?:ReadAll\w+|OpenRead|ReadLines)\s*\(\s*([^,)]*)")),
        ("file", "reads", re.compile(r"new\s+StreamReader\s*\(\s*([^,)]*)")),
        ("job", "runs", re.compile(r"\b(RecurringJob\.\w+|:\s*BackgroundService\b|IHostedService\b|"
                                   r"CronScheduleBuilder|WithCronSchedule)")),
        ("db", "defines", re.compile(r"\[Table\s*\(\s*" + _S)),
        ("db", "defines", re.compile(r"DbSet<\s*(\w+)\s*>")),
        ("http", "exposes", re.compile(r"\[(ServiceContract)\b")),
    ],
    "js": [
        ("http", "exposes", re.compile(r"\b(?:app|router)\.(?:get|post|put|delete|patch|all)\s*\(\s*[\"'`]([^\"'`]+)")),
        ("http", "consumes", re.compile(r"\b(fetch\s*\(|axios\.\w+|\$http\.\w+|http\.request\s*\()")),
        ("file", "writes", re.compile(r"fs\.(?:writeFile\w*|appendFile\w*|createWriteStream)\s*\(\s*([^,)]*)")),
        ("file", "reads", re.compile(r"fs\.(?:readFile\w*|createReadStream)\s*\(\s*([^,)]*)")),
        ("job", "runs", re.compile(r"\b(cron\.schedule|new\s+CronJob|node-schedule)")),
    ],
    "go": [
        ("http", "exposes", re.compile(r"\b(?:http\.)?HandleFunc\s*\(\s*\"([^\"]+)\"")),
        ("http", "consumes", re.compile(r"\b(http\.(?:Get|Post|PostForm|Head|NewRequest(?:WithContext)?))\s*\(")),
        ("file", "writes", re.compile(r"\bos\.(?:Create|WriteFile|OpenFile)\s*\(\s*([^,)]*)")),
        ("file", "reads", re.compile(r"\bos\.(?:Open|ReadFile)\s*\(\s*([^,)]*)")),
        ("job", "runs", re.compile(r"\b(?:\w+\.)?AddFunc\s*\(\s*\"([^\"]+)\"")),
    ],
    "php": [
        ("http", "exposes", re.compile(r"Route::(?:get|post|put|patch|delete|any|match)\s*\(\s*" + _S)),
        ("http", "exposes", re.compile(r"(?:#\[Route|@Route)\s*\(\s*" + _S)),
        ("http", "consumes", re.compile(r"\b(curl_init|Http::\w+|GuzzleHttp|file_get_contents\s*\(\s*[\"']https?://)")),
        ("file", "writes", re.compile(r"\bfile_put_contents\s*\(\s*([^,)]*)")),
        ("file", "writes", re.compile(r"\bfopen\s*\(\s*([^,)]*)\s*,\s*[\"'][wax]")),
        ("file", "reads", re.compile(r"\bfopen\s*\(\s*([^,)]*)\s*,\s*[\"']r")),
        ("job", "runs", re.compile(r"->(cron\s*\(\s*[\"'][^\"']+[\"']|everyMinute|hourly|daily\w*|weekly\w*|monthly\w*)\s*\(")),
    ],
    "ruby": [
        ("http", "exposes", re.compile(r"^\s*(?:get|post|put|patch|delete)\s+" + _S)),
        ("http", "exposes", re.compile(r"^\s*resources?\s+:(\w+)")),
        ("http", "consumes", re.compile(r"\b(Net::HTTP|HTTParty|Faraday|RestClient)\b")),
        ("file", "writes", re.compile(r"\bFile\.(?:write|open\s*\(\s*[^,)]+,\s*[\"'][wa])\s*\(?\s*([^,)]*)")),
        ("file", "reads", re.compile(r"\bFile\.(?:read|readlines|foreach)\s*\(\s*([^,)]*)")),
        ("job", "runs", re.compile(r"^\s*every\s+([^,]+?)\s*(?:,|do\b)")),
        ("db", "defines", re.compile(r"self\.table_name\s*=\s*" + _S)),
    ],
    "cobol": [
        ("file", "uses", re.compile(r"(?i)\bSELECT\s+[\w-]+\s+ASSIGN\s+TO\s+([\w.'\"-]+)")),
        ("rpc", "consumes", re.compile(r"(?i)\bEXEC\s+CICS\s+(?:LINK|XCTL)\s+PROGRAM\s*\(\s*'?([\w-]+)")),
        ("ui", "exposes", re.compile(r"(?i)\bEXEC\s+CICS\s+SEND\s+MAP\s*\(\s*'?([\w-]+)")),
        ("queue", "produces", re.compile(r"(?i)\bCALL\s+'(MQPUT1?)'")),
        ("queue", "consumes", re.compile(r"(?i)\bCALL\s+'(MQGET)'")),
    ],
    "jcl": [
        ("file", "uses", re.compile(r"(?i)^//[\w#@$]*\s+DD\s+.*\bDSN=([\w.#@$()+-]+)")),
        ("job", "runs", re.compile(r"(?i)^//[\w#@$]*\s+EXEC\s+PGM=([\w#@$]+)")),
    ],
}
_RULES["vb"] = [r for r in _RULES["csharp"] if r[0] != "http" or r[1] != "exposes"]
_VB_ROUTE = re.compile(r"(?i)<Route\s*\(\s*" + _S)
_VB_VERB = re.compile(r"(?i)<Http(Get|Post|Put|Delete|Patch)(?:\s*\(\s*" + _S + r")?")
_GO_ROUTER = re.compile(r"\b\w+\.(GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete|Patch)\s*\(\s*\"(/[^\"]*)\"")
_COBOL_SQL = re.compile(r"(?i)\bEXEC\s+SQL\b")

# ── declared contracts (the strongest evidence: what the system promises) ─────
_OPENAPI_MARKER = re.compile(r"(?m)^\s*[\"']?(openapi|swagger)[\"']?\s*:")
_OPENAPI_PATH = re.compile(r"^\s{1,6}[\"']?(/[^\"'\s:]*)[\"']?\s*:\s*\{?\s*$")
_WSDL_OPERATION = re.compile(r"<(?:wsdl:)?operation\s+name=\"([^\"]+)\"")
_PROTO_SERVICE = re.compile(r"^\s*service\s+(\w+)")
_PROTO_RPC = re.compile(r"^\s*rpc\s+(\w+)\s*\(")
_GRAPHQL_ROOT = re.compile(r"^\s*(?:extend\s+)?type\s+(Query|Mutation|Subscription)\b")
_GRAPHQL_FIELD = re.compile(r"^\s+(\w+)\s*[(:]")
_K8S_CRONJOB = re.compile(r"(?m)^\s*kind:\s*CronJob\s*$")
_K8S_SCHEDULE = re.compile(r"^\s*schedule:\s*[\"']?([^\"'\n#]+)")

_CS_ROUTE = re.compile(r"\[Route\s*\(\s*" + _S)
_CS_VERB = re.compile(r"\[Http(Get|Post|Put|Delete|Patch)(?:\s*\(\s*" + _S + r")?")
_CS_MINIMAL = re.compile(r"\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*" + _S)
_PY_OPEN = re.compile(r"\bopen\s*\(")
_PY_MODE = re.compile(r"""^\s*(?:mode\s*=\s*)?["']([rwabxt+]+)["']\s*$""")
_PY_WRITES = re.compile(r"\.(to_csv|to_excel|to_json)\s*\(\s*([^,)]*)")

_SQL_TABLE = re.compile(r"(?i)\b(from|into|update|join)\s+[`\"\[]?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)")
_SQL_CREATE = re.compile(r"(?i)\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?[`\"\[]?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)")
_SQL_NOT_TABLES = frozenset({"dual", "select", "where", "set", "values", "information_schema", "sysdate", "table",
                             "the", "a", "an", "this", "that", "to", "and", "or", "on", "as",
                             "from", "into", "update", "join", "server", "cache", "file", "disk"})
#: In a STRING the keyword only names a table when the statement around it is SQL-shaped — so
#: "Failed to update from server cache" is not `UPDATE from` (review fix #7).
_SQL_SHAPE = {
    "from": re.compile(r"(?i)\b(select|delete)\b"),
    "join": re.compile(r"(?i)\bselect\b"),
    "into": re.compile(r"(?i)\b(insert|merge)\b"),
    "update": re.compile(r"(?i)\bupdate\s+[`\"\[]?[A-Za-z_][\w$.]*[`\"\]]?\s+set\b"),
}
_STRING_LITERAL = re.compile(r"\"((?:[^\"\\]|\\.){6,})\"|'((?:[^'\\]|\\.){6,})'")

_WEB_XML_PATTERN = re.compile(r"<url-pattern>\s*([^<\s]+)\s*</url-pattern>")
_CRON_EXPRESSION = re.compile(r"<cron-expression>\s*([^<]+?)\s*</cron-expression>|\bcron\s*[=:]\s*[\"']?([^\"'\n]+)")

#: Languages whose code is scanned. Anything else (VB.NET, Go, COBOL, …) is NOT scanned — the
#: inventory lists nothing for it, which is "not scanned", never "no interfaces".
_LANG_BY_EXT = {".java": "java", ".kt": "java", ".groovy": "java", ".scala": "java", ".py": "python",
                ".cs": "csharp", ".vb": "vb", ".js": "js", ".mjs": "js", ".cjs": "js", ".ts": "js",
                ".go": "go", ".php": "php", ".rb": "ruby", ".cbl": "cobol", ".cob": "cobol", ".cobol": "cobol",
                ".cpy": "cobol", ".jcl": "jcl"}
SCANNED = ("Java/Kotlin/Groovy/Scala", "C#", "VB.NET", "Python", "JavaScript/TypeScript", "Go", "PHP", "Ruby",
           "COBOL", "JCL", "SQL", "web.xml", "JSP/ASPX/ASMX/SVC pages", "OpenAPI/Swagger", "WSDL", "gRPC .proto",
           "GraphQL schemas", "cron, Quartz and Kubernetes CronJob schedules")
_PAGE_EXT = {".jsp": "JSP page", ".jspx": "JSP page", ".aspx": "ASP.NET page", ".asmx": "ASMX web service",
             ".svc": "WCF service"}


# ── scanning ─────────────────────────────────────────────────────────────────


def _files(root: Path) -> Iterable[Path]:
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith("."))
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        for name in sorted(filenames):
            if is_vendored_asset("" if rel_dir == "." else rel_dir, name):
                continue
            path = Path(dirpath) / name
            # A cloned repository can carry a symlink to anywhere on this server (another
            # project's checkout, host configuration). Never followed (review fix #6).
            if path.is_symlink():
                continue
            seen += 1
            if seen > _MAX_FILES:
                return
            yield path


def _read(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def _clean(value: str) -> str:
    """A name as people read it: the string literal when the match holds one
    (`Paths.get("/data/x.csv")` → `/data/x.csv`), else the expression, trimmed."""
    value = value or ""
    quoted = _QUOTED.search(value)
    if quoted:
        return quoted.group(1).strip()[:160]
    return value.strip().strip("\"'`").strip()[:160]


def _join(prefix: str, path: str) -> str:
    prefix, path = (prefix or "").strip(), (path or "").strip()
    if not prefix:
        return path or "/"
    if not path:
        return prefix
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def _java(lines: list[str], rel: str, emit) -> None:
    """Spring MVC and JAX-RS with their class-level prefixes, plus the generic rules."""
    prefix = ""
    class_seen = False
    for n, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        if not class_seen:
            m = _JAVA_CLASS_MAPPING.search(line) or _JAXRS_PATH.search(line)
            if m:
                prefix = m.group(1)
                continue
            if _CLASS_DECL.search(line):
                class_seen = True
            continue
        m = _JAVA_METHOD_MAPPING.search(line)
        if m:
            verb = m.group(1).upper()
            if verb == "REQUEST":
                rm = _JAVA_REQUEST_METHOD.search(line)
                verb = rm.group(1).upper() if rm else "ANY"
            emit("http", "exposes", f"{verb} {_join(prefix, m.group(2) or '')}", n, line)
            continue
        v = _JAXRS_VERB.search(line)
        if v:
            # JAX-RS puts @GET and the method's @Path in either order, among the method's
            # OTHER ANNOTATIONS — so look only through that annotation block, never into the
            # next method's (review fix #7: a bare @GET borrowed its neighbour's @Path).
            path = ""
            for i in [*_annotation_block(lines, n - 1, -1), *_annotation_block(lines, n - 1, +1)]:
                p = _JAXRS_PATH.search(lines[i])
                if p:
                    path = p.group(1)
                    break
            emit("http", "exposes", f"{v.group(1)} {_join(prefix, path)}", n, line)


def _annotation_block(lines: list[str], index: int, step: int, limit: int = 4) -> list[int]:
    """The indexes of the annotation lines next to `index` in one direction (nearest first)."""
    out, i = [], index + step
    while 0 <= i < len(lines) and len(out) < limit and lines[i].strip().startswith("@"):
        out.append(i)
        i += step
    return out


def _csharp(lines: list[str], rel: str, emit) -> None:
    """Attribute routes: the controller's [Route] (before the class) is the prefix; a method's
    own [Route] joins it — it never replaces it (review fix #7)."""
    prefix = ""
    class_seen = False
    method_route: Optional[tuple[str, int]] = None
    for n, line in enumerate(lines, 1):
        route = _CS_ROUTE.search(line)
        verb = _CS_VERB.search(line)
        if not class_seen:
            if route and not verb:
                prefix = route.group(1).replace("[controller]", Path(rel).stem.removesuffix("Controller").lower())
                continue
            if _CLASS_DECL.search(line):
                class_seen = True
        elif route and not verb:
            method_route = (route.group(1), n)
            continue
        if verb:
            own = method_route[0] if method_route and n - method_route[1] <= 3 else ""
            emit("http", "exposes", f"{verb.group(1).upper()} {_join(_join(prefix, own) if own else prefix, verb.group(2) or '')}",
                 n, line)
            method_route = None
        minimal = _CS_MINIMAL.search(line)
        if minimal:
            emit("http", "exposes", f"{minimal.group(1).upper()} {minimal.group(2)}", n, line)


def _call_args(text: str, start: int) -> list[str]:
    """The top-level arguments of the call whose `(` is at `start` (to the end of the line)."""
    args, depth, current, quote = [], 0, [], ""
    for ch in text[start + 1:]:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    args.append("".join(current).strip())
    return [a for a in args if a]


def _python(lines: list[str], rel: str, emit) -> None:
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith("#"):
            continue
        for m in _PY_OPEN.finditer(line):
            # Arguments split at the TOP level, so `open(os.path.join(OUT, "x.csv"), "w")` is a
            # write of the joined path, not a read of `os.path.join(OUT` (review fix #7).
            args = _call_args(line, m.end() - 1)
            if not args:
                continue
            mode = next((mm.group(1) for a in args[1:] if (mm := _PY_MODE.match(a))), "r")
            emit("file", "writes" if any(c in mode for c in "wax") else "reads", _clean(args[0]), n, line)
        m = _PY_WRITES.search(line)
        if m:
            emit("file", "writes", _clean(m.group(2)) or m.group(1), n, line)


def _sql_in_strings(lines: list[str], emit) -> None:
    for n, line in enumerate(lines, 1):
        for lit in _STRING_LITERAL.finditer(line):
            text = lit.group(1) or lit.group(2) or ""
            for t in _SQL_TABLE.finditer(text):
                if t.group(2).lower() not in _SQL_NOT_TABLES and _SQL_SHAPE[t.group(1).lower()].search(text):
                    emit("db", "uses", t.group(2), n, line)


def _sql_file(lines: list[str], emit) -> None:
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith("--"):
            continue
        for t in _SQL_CREATE.finditer(line):
            emit("db", "defines", t.group(1), n, line)
        for t in _SQL_TABLE.finditer(line):
            if t.group(2).lower() not in _SQL_NOT_TABLES:
                emit("db", "uses", t.group(2), n, line)


def _is_comment(lang: str, line: str) -> bool:
    s = line.lstrip()
    if lang == "jcl":
        return s.startswith("//*")  # every JCL statement starts with //; only //* is a comment
    if lang == "cobol":  # fixed format: an asterisk in column 7; free format: *>
        return (len(line) > 6 and line[6] in "*/") or s.startswith(("*>", "*"))
    if lang == "vb":
        return s.startswith("'")
    if lang == "php":  # `#[Route]` is a PHP 8 attribute; Symfony's `* @Route` lives in docblocks — both are code
        if s.startswith("#[") or (s.startswith("*") and "@Route" in s):
            return False
    return s.startswith(("//", "#", "*"))


def _vb(lines: list[str], emit) -> None:
    """VB.NET attribute routes: `<Route("api/x")>` on the class is the prefix; method routes join it."""
    prefix, class_seen = "", False
    for n, line in enumerate(lines, 1):
        route, verb = _VB_ROUTE.search(line), _VB_VERB.search(line)
        if not class_seen:
            if route and not verb:
                prefix = route.group(1)
                continue
            if re.search(r"(?i)\bClass\s+\w+", line):
                class_seen = True
        if verb:
            emit("http", "exposes", f"{verb.group(1).upper()} {_join(prefix, verb.group(2) or '')}", n, line)


def _go(lines: list[str], emit) -> None:
    """Router registrations (gin, echo, chi, gorilla): `r.GET("/x", h)`."""
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith("//"):
            continue
        for m in _GO_ROUTER.finditer(line):
            emit("http", "exposes", f"{m.group(1).upper()} {m.group(2)}", n, line)


def _cobol_sql(lines: list[str], emit) -> None:
    """Embedded SQL: `EXEC SQL … END-EXEC` spans lines, so the statement is joined first and
    its tables reported at the line where it starts."""
    i = 0
    while i < len(lines):
        if _COBOL_SQL.search(lines[i]) and not _is_comment("cobol", lines[i]):
            start, parts = i, []
            while i < len(lines):
                parts.append(lines[i])
                if "END-EXEC" in lines[i].upper():
                    break
                i += 1
            statement = " ".join(parts)
            for t in _SQL_TABLE.finditer(statement):
                if t.group(2).lower() not in _SQL_NOT_TABLES and _SQL_SHAPE[t.group(1).lower()].search(statement):
                    emit("db", "uses", t.group(2), start + 1, lines[start])
        i += 1


_DECLARED_EXT = {".yaml", ".yml", ".json", ".wsdl", ".proto", ".graphql", ".graphqls", ".gql"}


def _declared(ext: str, text: str, lines: list[str], emit) -> None:
    """What a DECLARED contract file promises its consumers: OpenAPI/Swagger paths, WSDL
    operations, gRPC services, GraphQL root fields, and Kubernetes CronJob schedules."""
    if ext in (".yaml", ".yml", ".json") and _OPENAPI_MARKER.search(text):
        in_paths = False
        for n, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.match(r"^[\"']?paths[\"']?\s*:", stripped):
                in_paths = True
                continue
            if in_paths:
                m = _OPENAPI_PATH.match(line)
                if m:
                    emit("http", "exposes", f"{m.group(1)} (declared)", n, line)
                elif line and not line[0].isspace() and not stripped.startswith(("}", "]", "#")):
                    in_paths = False  # the next top-level key
    if ext in (".yaml", ".yml") and _K8S_CRONJOB.search(text):
        for n, line in enumerate(lines, 1):
            m = _K8S_SCHEDULE.match(line)
            if m:
                emit("job", "runs", m.group(1).strip(), n, line)
    if ext == ".wsdl":
        for n, line in enumerate(lines, 1):
            for m in _WSDL_OPERATION.finditer(line):
                emit("rpc", "exposes", f"SOAP {m.group(1)}", n, line)
    if ext == ".proto":
        service = ""
        for n, line in enumerate(lines, 1):
            s = _PROTO_SERVICE.match(line)
            if s:
                service = s.group(1)
            r = _PROTO_RPC.match(line)
            if r:
                emit("rpc", "exposes", f"gRPC {service + '.' if service else ''}{r.group(1)}", n, line)
    if ext in (".graphql", ".graphqls", ".gql"):
        root = ""
        for n, line in enumerate(lines, 1):
            t = _GRAPHQL_ROOT.match(line)
            if t:
                root = t.group(1)
                continue
            if line.strip().startswith("}"):
                root = ""
                continue
            f = _GRAPHQL_FIELD.match(line)
            if root and f:
                emit("rpc", "exposes", f"GraphQL {root}.{f.group(1)}", n, line)


def _module_for(rel: str, modules: list[dict]) -> str:
    """The module whose path is the longest prefix of `rel` — its id when it has one."""
    best, best_len = "", -1
    for m in modules:
        path = (m.get("path") or "").strip("/")
        if path in ("", "."):
            length = 0
        elif rel == path or rel.startswith(path + "/"):
            length = len(path)
        else:
            continue
        if length > best_len:
            best, best_len = str(m.get("id") or m.get("name") or ""), length
    return best


def capture_interfaces(root: str | os.PathLike, modules: Optional[list[dict]] = None,
                       commit: str = "") -> dict:
    """The legacy system's interface inventory. Deterministic for a given checkout.

    `modules` ([{id, name, path}]) attributes each entry to a module; the assessment's are best
    (ids), the pull profile's names will do.
    """
    root = Path(root)
    modules = list(modules or [])
    found: dict[tuple, Interface] = {}

    def add(rel: str):
        def emit(kind: str, direction: str, name: str, line_no: int, line: str) -> None:
            name = _clean(name) or "(unnamed)"
            key = (kind, direction, name, rel)
            if key in found:
                return
            found[key] = Interface(kind=kind, direction=direction, name=name, location=f"{rel}:{line_no}",
                                   module=_module_for(rel, modules), evidence=line.strip()[:200])
        return emit

    for path in _files(root):
        rel = path.relative_to(root).as_posix()
        ext = path.suffix.lower()
        name = path.name.lower()
        if ext in _PAGE_EXT:
            add(rel)("http", "exposes", f"{_PAGE_EXT[ext]} /{rel}", 1, _PAGE_EXT[ext])
            if ext not in (".svc", ".asmx"):
                continue
        lang = _LANG_BY_EXT.get(ext)
        is_sql = ext == ".sql"
        is_web_xml = name == "web.xml"
        is_cron = name in ("crontab", "cron.txt") or ext == ".cron" or name.startswith("quartz") \
            or ext in (".properties", ".yml", ".yaml") and "cron" in name
        declared = ext in _DECLARED_EXT
        if not (lang or is_sql or is_web_xml or is_cron or declared
                or ext in (".properties", ".yml", ".yaml", ".xml")):
            continue
        text = _read(path)
        if text is None:
            continue
        lines = text.splitlines()
        emit = add(rel)
        if declared:
            _declared(ext, text, lines, emit)
        if is_web_xml:
            for n, line in enumerate(lines, 1):
                for m in _WEB_XML_PATTERN.finditer(line):
                    emit("http", "exposes", f"servlet {m.group(1)}", n, line)
        if ext in (".properties", ".yml", ".yaml", ".xml") or is_cron:
            for n, line in enumerate(lines, 1):
                m = _CRON_EXPRESSION.search(line)
                if m:
                    emit("job", "runs", m.group(1) or m.group(2), n, line)
        if is_cron and not ext:
            for n, line in enumerate(lines, 1):
                if line.strip() and not line.lstrip().startswith("#"):
                    emit("job", "runs", line.strip(), n, line)
        if is_sql:
            _sql_file(lines, emit)
            continue
        if not lang:
            continue
        if lang == "java":
            _java(lines, rel, emit)
        elif lang == "csharp":
            _csharp(lines, rel, emit)
        elif lang == "vb":
            _vb(lines, emit)
        elif lang == "python":
            _python(lines, rel, emit)
        elif lang == "go":
            _go(lines, emit)
        elif lang == "cobol":
            _cobol_sql(lines, emit)
        for kind, direction, pattern in _RULES[lang]:
            for n, line in enumerate(lines, 1):
                if _is_comment(lang, line):
                    continue
                m = pattern.search(line)
                if not m:
                    continue
                name_ = m.group(1) if m.groups() and m.group(1) else m.group(0)
                if kind == "http" and direction == "consumes":
                    url = _URL_LITERAL.search(line)
                    name_ = url.group(1) if url else name_
                emit(kind, direction, name_, n, line)
        _sql_in_strings(lines, emit)

    items = sorted(found.values(), key=lambda i: (KINDS.index(i.kind), i.location, i.direction, i.name))
    counts = {k: sum(1 for i in items if i.kind == k) for k in KINDS}
    truncated = len(items) > MAX_ITEMS
    return {
        "commit": commit,
        "counts": counts,
        "total": len(items),
        "truncated": truncated,
        "items": [asdict(i) for i in items[:MAX_ITEMS]],
    }


def files_with_interfaces(inventory: dict) -> set[str]:
    """Every file an inventory entry points at (the path part of `location`)."""
    return set(lines_by_file(inventory))


def lines_by_file(inventory: dict) -> dict[str, list[int]]:
    """file → the lines inventory entries point at: what `checks.check_locations` confirms against."""
    out: dict[str, list[int]] = {}
    for i in inventory.get("items") or []:
        file, _, line = i["location"].rpartition(":")
        out.setdefault(file, []).append(int(line) if line.isdigit() else 0)
    return out


_KIND_TITLE = {"http": "HTTP endpoints and calls", "rpc": "RPC operations (SOAP, gRPC, GraphQL, CICS)",
               "file": "Files and datasets written and read", "job": "Scheduled jobs", "db": "Database tables",
               "queue": "Queues and topics", "ui": "Screens"}


def interfaces_markdown(inventory: dict, max_per_kind: int = 40) -> str:
    """The inventory as a report the agent reads and quotes locations from."""
    counts = inventory.get("counts") or {}
    items = inventory.get("items") or []
    lines = ["# Legacy interface inventory", ""]
    if inventory.get("commit"):
        lines.append(f"Commit `{str(inventory['commit'])[:12]}`. Found by pattern scan of the code — "
                     "cite locations exactly; anything not listed here is unproven.")
    lines.append("Totals: " + ", ".join(f"{_KIND_TITLE[k].lower()} {counts.get(k, 0)}" for k in KINDS) + ".")
    lines.append("Scanned: " + ", ".join(SCANNED) + ". Code in any other language was NOT scanned — no entry "
                 "for it means not scanned, not \"no interfaces\".")
    if inventory.get("truncated"):
        lines.append(f"(The inventory is capped at {MAX_ITEMS} entries; {inventory.get('total')} were found.)")
    for kind in KINDS:
        rows = [i for i in items if i["kind"] == kind]
        if not rows:
            continue
        lines += ["", f"## {_KIND_TITLE[kind]} ({len(rows)})", "", "| Direction | Name | Where | Module |",
                  "|---|---|---|---|"]
        for i in rows[:max_per_kind]:
            lines.append(f"| {i['direction']} | `{i['name'].replace('|', '/')}` | `{i['location']}` | {i['module'] or '—'} |")
        if len(rows) > max_per_kind:
            lines.append(f"| … | {len(rows) - max_per_kind} more | | |")
    return "\n".join(lines)
