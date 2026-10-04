<?php
declare(strict_types=1);

require_once __DIR__ . '/../app/Controllers/ChatController.php';

$controller = new ChatController();
$controller->reply();
