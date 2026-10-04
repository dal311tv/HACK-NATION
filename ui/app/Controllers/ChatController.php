<?php
declare(strict_types=1);

require_once __DIR__ . '/../Models/OpenAIChatModel.php';

final class ChatController
{
    public function showPage(): void
    {
        require __DIR__ . '/../Views/chat.php';
    }

    public function reply(): never
    {
        header('Content-Type: application/json; charset=utf-8');
        header('X-Content-Type-Options: nosniff');

        if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
            header('Allow: POST');
            $this->respond(405, ['error' => 'Método no permitido.']);
        }

        $request = json_decode((string) file_get_contents('php://input'), true);
        $messages = $request['messages'] ?? null;
        if (!is_array($messages) || count($messages) < 1 || count($messages) > 40) {
            $this->respond(400, ['error' => 'Envía entre 1 y 40 mensajes.']);
        }

        $validMessages = [];
        foreach ($messages as $message) {
            if (!is_array($message)
                || !in_array($message['role'] ?? '', ['user', 'assistant'], true)
                || !is_string($message['content'] ?? null)) {
                $this->respond(400, ['error' => 'El formato de la conversación no es válido.']);
            }

            $content = trim($message['content']);
            if ($content === '' || strlen($content) > 48000) {
                $this->respond(400, ['error' => 'Cada mensaje debe tener texto y no exceder 12,000 caracteres.']);
            }
            $validMessages[] = ['role' => $message['role'], 'content' => $content];
        }

        try {
            $model = new OpenAIChatModel();
            $this->respond(200, ['reply' => $model->createReply($validMessages)]);
        } catch (RuntimeException $exception) {
            $this->respond(502, ['error' => $exception->getMessage()]);
        }
    }

    private function respond(int $status, array $body): never
    {
        http_response_code($status);
        echo json_encode($body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        exit;
    }
}
