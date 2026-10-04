<?php
declare(strict_types=1);

// Read-only view of the research ledger. Never writes to any file.

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');

$repoRoot = dirname(__DIR__, 2);
$candidates = [
    $repoRoot . '/ledger/ledger.jsonl',
    $repoRoot . '/ledger/example_ledger.jsonl',
];

$path = null;
foreach ($candidates as $candidate) {
    if (is_file($candidate) && is_readable($candidate)) {
        $path = $candidate;
        break;
    }
}

if ($path === null) {
    http_response_code(404);
    echo json_encode(['error' => 'No ledger file found.', 'source' => null, 'entries' => [], 'invalid_lines' => 0]);
    exit;
}

$lines = file($path, FILE_IGNORE_NEW_LINES);
if ($lines === false) {
    http_response_code(500);
    echo json_encode(['error' => 'Could not read the ledger file.', 'source' => basename($path), 'entries' => [], 'invalid_lines' => 0]);
    exit;
}

$entries = [];
$invalid = 0;
foreach ($lines as $line) {
    $line = trim($line);
    if ($line === '') {
        continue;
    }
    // Decode as objects so empty {} payloads survive re-encoding unchanged.
    try {
        $entry = json_decode($line, false, 512, JSON_THROW_ON_ERROR);
    } catch (JsonException) {
        $invalid++;
        continue;
    }
    if (!$entry instanceof stdClass) {
        $invalid++;
        continue;
    }
    $entries[] = $entry;
}

echo json_encode(
    ['source' => basename($path), 'entries' => $entries, 'invalid_lines' => $invalid],
    JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION | JSON_INVALID_UTF8_SUBSTITUTE
);
