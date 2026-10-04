<?php
declare(strict_types=1);

// Main page: read-only Mission Control dashboard. The chat lives at chat.php.
require_once __DIR__ . '/app/Controllers/DashboardController.php';

$controller = new DashboardController();
$controller->showPage();
