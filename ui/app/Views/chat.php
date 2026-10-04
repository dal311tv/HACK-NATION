<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#101113">
  <title>Chat | Navegador IA</title>
  <style>
    :root{color-scheme:dark;--bg:#101113;--panel:#17181b;--line:#2a2c30;--muted:#a0a2aa;--text:#f5f5f6;--accent:#b8f28b}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;height:100vh;display:grid;grid-template-rows:42px 1fr}
    .chrome{display:flex;align-items:center;gap:12px;padding:0 16px;background:#1a1b1e;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px}.lights{display:flex;gap:6px}.lights i{width:9px;height:9px;border-radius:50%;background:#56585e}.address{margin:auto;width:min(420px,60vw);text-align:center;background:#242529;border:1px solid #303136;border-radius:8px;padding:4px 12px;color:#d0d1d4}
    .layout{min-height:0;display:grid;grid-template-columns:245px 1fr}.side{background:#151619;border-right:1px solid var(--line);padding:20px 14px}.brand{display:flex;align-items:center;gap:10px;font-weight:650;margin:2px 5px 27px}.logo{display:grid;place-items:center;width:28px;height:28px;border-radius:9px;background:var(--accent);color:#141711;font-weight:800}.new{width:100%;border:1px solid #3a3c40;background:transparent;color:var(--text);padding:10px;border-radius:9px;text-align:left;cursor:pointer}.hint{margin:18px 6px;color:var(--muted);font-size:12px}.sidebar-foot{position:absolute;bottom:18px;color:var(--muted);font-size:12px;padding:0 6px;max-width:220px}
    main{display:flex;flex-direction:column;min-width:0;min-height:0}.top{height:56px;display:flex;align-items:center;padding:0 26px;border-bottom:1px solid #222327;font-size:14px}.top small{color:var(--muted);margin-left:8px}.conversation{flex:1;overflow:auto;padding:35px 20px 20px}.welcome{max-width:720px;margin:12vh auto 0;text-align:center}.welcome h1{font-size:30px;font-weight:550;letter-spacing:-.6px;margin:0 0 10px}.welcome p{color:var(--muted);margin:0}.messages{width:min(760px,100%);margin:0 auto}.message{display:flex;gap:14px;margin:20px 0;align-items:flex-start}.avatar{flex:0 0 30px;height:30px;border-radius:50%;display:grid;place-items:center;background:#292b2f;color:var(--accent);font-size:12px;font-weight:700}.message.user .avatar{background:#384039;color:#d8f7c3}.body{padding:3px 0;white-space:pre-wrap;overflow-wrap:anywhere}.message.assistant .body{color:#e7e7e9}.error{color:#ffaaa8!important}
    .composer-wrap{padding:12px 20px 22px}.composer{width:min(760px,100%);margin:auto;border:1px solid #3a3c41;border-radius:16px;background:#1b1c1f;padding:12px;box-shadow:0 8px 30px #0002}.composer textarea{display:block;width:100%;resize:none;min-height:42px;max-height:180px;border:0;outline:0;background:transparent;color:var(--text);font:inherit;padding:4px 5px}.composer-bottom{display:flex;align-items:center;justify-content:space-between;padding:5px 2px 0 6px;color:var(--muted);font-size:11px}.send{width:34px;height:34px;border:0;border-radius:10px;background:var(--accent);color:#151811;font-size:18px;cursor:pointer}.send:disabled{opacity:.5;cursor:wait}.notice{text-align:center;color:#888a90;font-size:11px;margin-top:9px}
    @media(max-width:680px){.layout{grid-template-columns:1fr}.side{display:none}.top{padding:0 18px}.welcome{margin-top:15vh}.welcome h1{font-size:25px}.conversation{padding:24px 16px}.composer-wrap{padding:10px 12px 15px}}
  </style>
</head>
<body>
  <div class="chrome"><span class="lights"><i></i><i></i><i></i></span><div class="address">✦ &nbsp; chat.local</div><span>⋯</span></div>
  <div class="layout">
    <aside class="side"><div class="brand"><span class="logo">✦</span> Navegador IA</div><button class="new" id="newChat">＋ &nbsp; Nuevo chat</button><div class="hint">Tu asistente de inteligencia artificial</div><div class="sidebar-foot">Las respuestas pueden contener errores. Verifica la información importante.</div></aside>
    <main><header class="top">Chat <small>· OpenAI</small></header>
      <section class="conversation" id="conversation" aria-live="polite"><div class="welcome" id="welcome"><h1>¿Qué tienes en mente?</h1><p>Escribe una pregunta para comenzar.</p></div><div class="messages" id="messages"></div></section>
      <div class="composer-wrap"><form class="composer" id="chatForm"><textarea id="prompt" rows="1" placeholder="Escribe tu mensaje…" aria-label="Escribe tu mensaje"></textarea><div class="composer-bottom"><span>Enter para enviar · Shift + Enter para nueva línea</span><button class="send" id="send" aria-label="Enviar">↑</button></div></form><div class="notice">La clave API se mantiene en el servidor PHP.</div></div>
    </main>
  </div>
  <script>
    const form=document.querySelector('#chatForm'), promptBox=document.querySelector('#prompt'), messagesEl=document.querySelector('#messages'), conversation=document.querySelector('#conversation'), welcome=document.querySelector('#welcome'), sendButton=document.querySelector('#send');
    let history=[];
    function addMessage(role,text,error=false){const row=document.createElement('div');row.className=`message ${role}`;const avatar=document.createElement('div');avatar.className='avatar';avatar.textContent=role==='user'?'T':'IA';const body=document.createElement('div');body.className='body'+(error?' error':'');body.textContent=text;row.append(avatar,body);messagesEl.append(row);conversation.scrollTop=conversation.scrollHeight;return body}
    promptBox.addEventListener('input',()=>{promptBox.style.height='auto';promptBox.style.height=Math.min(promptBox.scrollHeight,180)+'px'});
    promptBox.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit()}});
    form.addEventListener('submit',async e=>{e.preventDefault();const text=promptBox.value.trim();if(!text||sendButton.disabled)return;welcome.hidden=true;addMessage('user',text);history.push({role:'user',content:text});promptBox.value='';promptBox.style.height='auto';sendButton.disabled=true;const pending=addMessage('assistant','Pensando…');
      try{const res=await fetch('api/chat.php',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:history})});const data=await res.json();if(!res.ok)throw new Error(data.error||'No se pudo obtener respuesta.');pending.textContent=data.reply;history.push({role:'assistant',content:data.reply})}
      catch(err){pending.textContent=err.message;pending.classList.add('error');history.pop()}
      finally{sendButton.disabled=false;promptBox.focus();conversation.scrollTop=conversation.scrollHeight}
    });
    document.querySelector('#newChat').addEventListener('click',()=>{history=[];messagesEl.replaceChildren();welcome.hidden=false;promptBox.focus()});
  </script>
</body>
</html>
