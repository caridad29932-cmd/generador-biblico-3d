const $=id=>document.getElementById(id);
let scenes=[];
let referenceImageName="";
const starters=[
{title:"Apertura y contexto",purpose:"Establece el lugar, la época y la situación inicial."},
{title:"Presentación de personajes",purpose:"Presenta a los protagonistas y sus relaciones mediante acciones y primeros planos."},
{title:"Conflicto",purpose:"Muestra el problema central que pone en marcha la historia."},
{title:"Decisión",purpose:"Representa la decisión que cambia el rumbo de los protagonistas."},
{title:"Desarrollo",purpose:"Desarrolla los acontecimientos principales en orden cronológico."},
{title:"Clímax",purpose:"Representa el momento de mayor tensión o emoción."},
{title:"Resolución",purpose:"Muestra las consecuencias y cómo cambia la vida de los personajes."},
{title:"Cierre y reflexión",purpose:"Cierra con una imagen memorable y una reflexión fiel al relato."}
];
function makeScenes(){
 const title=$("title").value.trim(),story=$("story").value.trim(),cast=$("cast").value.trim(),look=$("look").value;
 if(!title||!story){$("planStatus").textContent="Escribe un título y la historia completa.";return}
 const parts=story.split(/(?<=[.!?])\s+/).filter(Boolean);
 const count=Math.min(120,Math.max(12,Math.ceil(Number($("length").value)/5)));
 scenes=Array.from({length:count},(_,i)=>{
  const start=Math.floor(i*parts.length/count),end=Math.max(start+1,Math.floor((i+1)*parts.length/count));
  const excerpt=parts.slice(start,end).join(" ")||story;
  const base=starters[Math.min(i,starters.length-1)];
  const prompt="PELÍCULA: "+title+"\nESCENA: "+(i+1)+" — "+base.title+"\nACCIÓN BASADA EN EL RELATO: "+excerpt+"\nOBJETIVO DRAMÁTICO: "+base.purpose+"\nPERSONAJES Y CONTINUIDAD: "+cast+"\nESTILO: "+look+". Cine bíblico respetuoso, ambientación histórica coherente, vestuario de época, composición cinematográfica, luz naturalista, movimientos humanos creíbles, cámara estable y profundidad de campo. Mantener exactamente la identidad visual de cada personaje en todas las escenas. Sin texto sobreimpreso, sin anacronismos, sin deformaciones.";
  return {title:base.title,excerpt,prompt};
 });
 $("castPreview").textContent=cast||"No se han definido personajes.";
 $("sceneCount").textContent=scenes.length+" ESCENAS";
 $("scenes").innerHTML="";
 scenes.forEach((s,i)=>{
  const card=document.createElement("article");card.className="scene";
  const h=document.createElement("h3");h.textContent=String(i+1).padStart(2,"0")+". "+s.title;
  const p=document.createElement("p");p.textContent=s.prompt;
  const b=document.createElement("button");b.className="secondary";b.textContent="COPIAR PROMPT";b.addEventListener("click",()=>copyText(s.prompt,b));
  const send=document.createElement("button");send.className="secondary";send.textContent="ENVIAR A MOTOR";send.addEventListener("click",()=>sendScene(i,send));
  card.append(h,p,b,send);$("scenes").append(card);
 });
 $("planStatus").textContent="Guion preparado: "+scenes.length+" clips de aproximadamente 5 segundos cada uno. Revisa las escenas; cada envío consume recursos del servidor GPU."
 $("narration").value=parts.join("\n\n");
}
async function copyText(value,button){try{await navigator.clipboard.writeText(value);button.textContent="COPIADO";setTimeout(()=>button.textContent="COPIAR PROMPT",1400)}catch(e){window.prompt("Copia el texto:",value)}}
function backend(){return $("backend").value.trim().replace(/\/$/,"")}
$("plan").addEventListener("click",makeScenes);
$("cast").addEventListener("input",()=>{$("castPreview").textContent=$("cast").value});
$("saveBackend").addEventListener("click",()=>{localStorage.setItem("betania_backend",backend());$("engineStatus").textContent="Dirección guardada en este dispositivo.";});

$("referenceImage").addEventListener("change",async e=>{
 const file=e.target.files[0];if(!file)return;
 if(!backend()){$("referenceStatus").textContent="Guarda primero la dirección del servidor GPU.";e.target.value="";return}
 if(file.size>10*1024*1024){$("referenceStatus").textContent="La imagen supera 10 MB.";e.target.value="";return}
 const form=new FormData();form.append("file",file);
 $("referenceStatus").textContent="Subiendo imagen de referencia...";
 try{
  const r=await fetch(backend()+"/api/reference",{method:"POST",body:form});
  if(!r.ok)throw Error("HTTP "+r.status);
  const data=await r.json();referenceImageName=data.image_name;
  $("referenceStatus").textContent="Referencia cargada. Se usará en cada escena enviada al motor.";
 }catch(err){referenceImageName="";$("referenceStatus").textContent="No se pudo subir la referencia: "+err.message}
});
\n$("backend").value=localStorage.getItem("betania_backend")||"";
async function testServer(){
 const url=backend();if(!url){$("engineStatus").textContent="Introduce la dirección de tu servidor.";return}
 $("engineStatus").textContent="Comprobando conexión...";
 try{const r=await fetch(url+"/health");if(!r.ok)throw Error("HTTP "+r.status);const data=await r.json();if(data.configured){$("engineState").textContent="CONECTADO";$("engineStatus").textContent="Servidor y ComfyUI disponibles. Motor: "+(data.engine||"Wan 2.2");}else{$("engineState").textContent="GPU PENDIENTE";$("engineStatus").textContent="La API responde, pero ComfyUI/Wan 2.2 todavía no está conectado."; }}
 catch(e){$("engineState").textContent="SIN CONECTAR";$("engineStatus").textContent="No se pudo verificar el servidor. Comprueba URL, CORS y que el backend esté activo. Detalle: "+e.message;}
}
$("testBackend").addEventListener("click",testServer);
async function sendScene(i,button){
 const url=backend();if(!url){$("engineStatus").textContent="Primero configura la dirección del servidor GPU.";return}
 if(!scenes[i])return;
 button.disabled=true;button.textContent="ENVIANDO...";
 try{
  const r=await fetch(url+"/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt:scenes[i].prompt,scene_index:i+1,title:$("title").value,reference_image:referenceImageName||null})});
  if(!r.ok)throw Error("HTTP "+r.status);
  const data=await r.json();const id=data.job_id;
  if(!id)throw Error("El servidor no devolvió job_id.");
  button.textContent="GENERANDO...";$("engineStatus").textContent="Escena enviada. Esperando el render del servidor GPU...";
  const started=Date.now();let done=false;
  while(Date.now()-started<900000){
   await new Promise(resolve=>setTimeout(resolve,5000));
   const check=await fetch(url+"/api/jobs/"+encodeURIComponent(id));
   if(!check.ok)throw Error("No se pudo consultar el trabajo: HTTP "+check.status);
   const state=await check.json();
   if(state.status==="completed"&&state.video_url){
    const v=document.createElement("video");v.controls=true;v.src=state.video_url.startsWith("http")?state.video_url:url+state.video_url;
    const title=document.createElement("p");title.textContent="Escena "+(i+1)+" — "+scenes[i].title;
    $("renderArea").append(title,v);button.textContent="VIDEO LISTO";$("engineStatus").textContent="Escena "+(i+1)+" renderizada correctamente.";done=true;break;
   }
   if(state.status==="failed")throw Error(state.error||"El motor informó un error.");
   $("engineStatus").textContent="Renderizando escena "+(i+1)+"... "+(state.status||"en cola");
  }
  if(!done)throw Error("El render sigue en proceso; vuelve a consultar el servidor.");
 }catch(e){button.disabled=false;button.textContent="REINTENTAR ESCENA";$("engineStatus").textContent="No se completó la escena: "+e.message}
}
function projectData(){return {app:"BETANIA",version:1,title:$("title").value,story:$("story").value,cast:$("cast").value,look:$("look").value,length:$("length").value,narration:$("narration").value,scenes:scenes}}
$("saveProject").addEventListener("click",()=>{const blob=new Blob([JSON.stringify(projectData(),null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="betania-proyecto.json";a.click();URL.revokeObjectURL(a.href)});
$("loadProject").addEventListener("click",()=>$("projectFile").click());
$("projectFile").addEventListener("change",async e=>{const f=e.target.files[0];if(!f)return;try{const d=JSON.parse(await f.text());$("title").value=d.title||"";$("story").value=d.story||"";$("cast").value=d.cast||"";$("look").value=d.look||$("look").options[0].value;$("length").value=d.length||"180";$("narration").value=d.narration||"";makeScenes();$("planStatus").textContent="Proyecto cargado. Se reconstruyeron las escenas a partir de la historia."; }catch(err){alert("No se pudo abrir el archivo JSON.")}});
makeScenes();