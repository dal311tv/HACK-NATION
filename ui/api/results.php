<?php
declare(strict_types=1);

// Read-only access to experiment results in <repo>/results/<run_id>/.
//   GET                       -> {"runs": [...], "latest_run": "<id>", "summary": {...}}
//   GET ?run_id=<id>          -> that run's summary.json
//   GET ?run_id=<id>&image=1  -> that run's recall_curves.png

const RUN_ID_PATTERN = '/^run-[A-Za-z0-9_-]+$/';

$resultsDir = dirname(__DIR__, 2) . '/results';

function respondJson(int $status, mixed $body): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('X-Content-Type-Options: nosniff');
    header('Cache-Control: no-store');
    echo json_encode(
        $body,
        JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION | JSON_INVALID_UTF8_SUBSTITUTE
    );
    exit;
}

function readSummary(string $runDir): ?stdClass
{
    $file = $runDir . '/summary.json';
    if (!is_file($file) || !is_readable($file)) {
        return null;
    }
    // Objects (not assoc arrays) keep {} and [] distinct when re-encoded.
    $summary = json_decode((string) file_get_contents($file), false);
    return $summary instanceof stdClass ? $summary : null;
}

/** @return list<string> run ids that contain summary.json, most recent first */
function listRuns(string $resultsDir): array
{
    if (!is_dir($resultsDir)) {
        return [];
    }
    $runs = [];
    foreach (scandir($resultsDir) ?: [] as $name) {
        if ($name === '.' || $name === '..' || str_starts_with($name, '_') || str_starts_with($name, '.')) {
            continue;
        }
        $summaryFile = $resultsDir . '/' . $name . '/summary.json';
        if (is_dir($resultsDir . '/' . $name) && is_file($summaryFile)) {
            $runs[$name] = (int) filemtime($summaryFile);
        }
    }
    // Newest summary first; ties (e.g. fresh git checkout) fall back to descending natural order of the id.
    uksort($runs, fn(string $a, string $b): int => ($runs[$b] <=> $runs[$a]) ?: strnatcmp($b, $a));
    return array_keys($runs);
}

$runId = $_GET['run_id'] ?? null;

if ($runId === null) {
    $runs = listRuns($resultsDir);
    $latest = $runs[0] ?? null;
    respondJson(200, [
        'runs' => $runs,
        'latest_run' => $latest,
        'summary' => $latest === null ? null : readSummary($resultsDir . '/' . $latest),
    ]);
}

if (!is_string($runId) || preg_match(RUN_ID_PATTERN, $runId) !== 1) {
    respondJson(400, ['error' => 'Invalid run_id.']);
}

$runDir = $resultsDir . '/' . $runId;
if (!is_dir($runDir)) {
    respondJson(404, ['error' => 'Run not found.']);
}

if (isset($_GET['image']) && $_GET['image'] === '1') {
    $image = $runDir . '/recall_curves.png';
    if (!is_file($image) || !is_readable($image)) {
        respondJson(404, ['error' => 'recall_curves.png not found for this run.']);
    }
    header('Content-Type: image/png');
    header('Content-Length: ' . filesize($image));
    header('X-Content-Type-Options: nosniff');
    header('Cache-Control: no-cache');
    readfile($image);
    exit;
}

$summary = readSummary($runDir);
if ($summary === null) {
    respondJson(404, ['error' => 'summary.json not found or not valid JSON for this run.']);
}
respondJson(200, $summary);
