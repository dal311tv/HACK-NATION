<?php
declare(strict_types=1);

final class DashboardController
{
    public function showPage(): void
    {
        header('Content-Type: text/html; charset=utf-8');
        require __DIR__ . '/../Views/dashboard.php';
    }
}
