<?php
declare(strict_types=1);

final class OpenAIChatModel
{
    public function createReply(array $messages): string
    {
        $apiKey = getenv('OPENAI_API_KEY');
        if (!$apiKey) {
            throw new RuntimeException('Falta configurar OPENAI_API_KEY en el servidor PHP.');
        }
        if (!function_exists('curl_init')) {
            throw new RuntimeException('PHP necesita tener habilitada la extensión cURL.');
        }

        $payload = json_encode([
            'model' => getenv('OPENAI_MODEL') ?: 'gpt-6-astra',
            'input' => $messages,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);

        $curl = curl_init('https://api.openai.com/v1/responses');
        curl_setopt_array($curl, [
            CURLOPT_POST => true,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER => [
                'Content-Type: application/json',
                'Authorization: Bearer ' . $apiKey,
            ],
            CURLOPT_POSTFIELDS => $payload,
            CURLOPT_CONNECTTIMEOUT => 15,
            CURLOPT_TIMEOUT => 90,
        ]);

        $raw = curl_exec($curl);
        $status = (int) curl_getinfo($curl, CURLINFO_HTTP_CODE);
        $curlError = curl_error($curl);
        curl_close($curl);

        if ($raw === false) {
            error_log('OpenAI cURL error: ' . $curlError);
            throw new RuntimeException('No se pudo conectar con OpenAI. Revisa la conexión del servidor e inténtalo de nuevo.');
        }

        $result = json_decode($raw, true);
        if ($status < 200 || $status >= 300) {
            $message = $result['error']['message'] ?? 'OpenAI devolvió un error.';
            error_log('OpenAI API error (' . $status . '): ' . $message);
            throw new RuntimeException('Error de OpenAI: ' . $message);
        }

        $reply = '';
        foreach (($result['output'] ?? []) as $item) {
            if (($item['type'] ?? '') !== 'message') {
                continue;
            }
            foreach (($item['content'] ?? []) as $part) {
                if (($part['type'] ?? '') === 'output_text') {
                    $reply .= $part['text'] ?? '';
                }
            }
        }

        if ($reply === '') {
            throw new RuntimeException('OpenAI no devolvió texto.');
        }
        return $reply;
    }
}
