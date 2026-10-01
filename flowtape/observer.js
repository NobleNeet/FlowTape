/* Protocol v1. This script is injected per document, including accessible frames. */
if (window.__flowtape && window.__flowtape.protocolVersion !== 1) throw Error('FlowTape protocol mismatch');
if (!window.__flowtape) {
  const state = window.__flowtape = {
    protocolVersion:1, documentInstanceId:crypto.randomUUID?.() || [...crypto.getRandomValues(new Uint8Array(16))].map(x=>x.toString(16).padStart(2,'0')).join(''), sequence:0,
    events:[], mode:'observe', overflow:false, composing:false, pendingInput:null,
    framePath:window===window.top?[]:null,
    refs:new Map(), elementIds:new WeakMap(), nextElementId:0,
    handlers:[], observedRoots:new WeakSet(),
    closedHosts:new WeakSet(),
    overlay:null,
    highlights:[],
    clearHighlights() {this.highlights.forEach(el=>el.remove());this.highlights=[];},
    highlight(elements) {
      this.clearHighlights();
      this.overlay?.remove();this.overlay=null;
      for(const el of elements) {
        const rect=el.getBoundingClientRect(), marker=document.createElement('div');
        marker.setAttribute('data-flowtape-overlay','');marker.setAttribute('aria-hidden','true');
        marker.style.cssText='position:fixed;pointer-events:none;z-index:2147483647;border:2px solid #147bd1;background:rgba(20,123,209,.08);box-sizing:border-box';
        Object.assign(marker.style,{left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px'});
        document.documentElement.append(marker);this.highlights.push(marker);
      }
    },
    setMode(mode) {
      this.mode=mode;
      if(!['pick','rebind','collection_pick'].includes(mode)) {this.overlay?.remove();this.overlay=null;}
    },
    drain() { const result=this.events; this.events=[]; return result; },
    emit(type, target, data={}) {
      if(target && (this.closedHosts.has(target) || target.localName==='canvas' || (target.localName==='input' && target.type==='file' && type==='click'))) {
        data={reason:this.closedHosts.has(target)?'closed_shadow':target.localName==='canvas'?'canvas_interaction':'native_file_picker'};
        type='unsupported';target=null;
      }
      if (this.events.length >= 1000) { this.overflow=true; return; }
      let ref=null;
      if(target) {
        ref=this.elementIds.get(target);
        if(!ref) {ref=++this.nextElementId; this.elementIds.set(target,ref);this.refs.set(ref,new WeakRef(target));}
      }
      const event={protocol_version:1,document_instance_id:this.documentInstanceId,
        event_seq:++this.sequence,timestamp:performance.timeOrigin+performance.now(),type,
        window_context:{frame_path:this.framePath},
        document:{url:location.href,title:document.title},
        target:target ? {snapshot:FT.snapshot(target),element_ref:ref} : null,data};
      this.events.push(event);
      if(typeof window.__flowtape_emit==='function') window.__flowtape_emit(JSON.stringify(event));
    },
    normalize(el) {
      return el?.closest('button,a[href],input,textarea,select,summary,[contenteditable],[role="button"],[role="link"],[role="checkbox"],[role="radio"],[role="tab"],[role="menuitem"]') || el;
    },
    flushInput() {
      if (this.pendingInput) { this.emit('input_commit',this.pendingInput.el,this.pendingInput.data); this.pendingInput=null; }
    }
  };
  const on = (name, fn) => {document.addEventListener(name, fn, true);state.handlers.push([name,fn]);};
  on('pointermove',e=>{
    if(!['pick','rebind','collection_pick'].includes(state.mode))return;
    const el=state.normalize(e.composedPath()[0]);if(!el)return;
    if(!state.overlay) {
      state.overlay=document.createElement('div');state.overlay.setAttribute('data-flowtape-overlay','');
      state.overlay.setAttribute('aria-hidden','true');
      state.overlay.style.cssText='position:fixed;pointer-events:none;z-index:2147483647;border:2px solid #147bd1;background:rgba(20,123,209,.08);box-sizing:border-box';
      document.documentElement.append(state.overlay);
    }
    const rect=el.getBoundingClientRect();
    Object.assign(state.overlay.style,{left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px'});
  });
  const picker = e => {
    if (!['pick','rebind','collection_pick'].includes(state.mode)) return false;
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    if (e.type === 'click') state.emit('pick',state.normalize(e.composedPath()[0]));
    return true;
  };
  ['pointerdown','mousedown','mouseup','click','dblclick'].forEach(type => on(type, e => {
    if (picker(e) || state.mode !== 'record') return;
    if (type === 'click' || type === 'dblclick') {
      if(state.normalize(e.composedPath()[0])?.localName==='select') return;
      state.flushInput(); state.emit(type,state.normalize(e.composedPath()[0]),{button:e.button});
    }
  }));
  on('compositionstart',()=>{state.composing=true;});
  on('compositionend',e=>{state.composing=false;const el=e.composedPath()[0]; if(state.pendingInput?.el===el) state.pendingInput.data.value=el.type==='password'?null:(el.value ?? el.innerText);});
  on('input',e=>{
    if(state.mode!=='record')return;
    const el=state.normalize(e.composedPath()[0]);
    if(!el || !(el.matches('input,textarea') || el.isContentEditable) || el.matches('input[type=checkbox],input[type=radio],input[type=file]')) return;
    const secret=el.type==='password';
    if(state.pendingInput && state.pendingInput.el!==el)state.flushInput();
    state.pendingInput={el,data:{value:secret?null:(el.value ?? el.innerText),secret}};
  });
  on('change',e=>{
    if(state.mode!=='record')return;
    const el=e.composedPath()[0];
    if(el.matches('select')) {
      state.flushInput();
      if(el.multiple) {
        state.emit('select',el,{multiple:true,values:[...el.selectedOptions].map(o=>o.value),texts:[...el.selectedOptions].map(o=>FT.norm(o.textContent))});
      } else {
        const option=el.selectedOptions[0];
        state.emit('select',el,{value:el.value,text:FT.norm(option?.textContent)});
      }
    } else if(state.pendingInput?.el===el && !state.composing) state.flushInput();
  });
  on('focusout',e=>{if(state.pendingInput?.el===e.composedPath()[0] && !state.composing)state.flushInput();});
  on('keydown',e=>{
    if(e.key==='Escape'&&['pick','rebind','collection_pick'].includes(state.mode)) {
      e.preventDefault();e.stopImmediatePropagation();state.emit('picker_cancel',null);state.setMode('observe');return;
    }
    if(state.mode!=='record'||state.composing||e.isComposing||e.keyCode===229)return;
    const el=e.composedPath()[0];
    const multiline=el?.matches?.('textarea')||el?.isContentEditable;
    if(e.key==='Enter'&&!multiline)state.flushInput();
    if((e.key==='Enter'&&!multiline)||['Escape','Tab','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End','PageUp','PageDown'].includes(e.key)||/^F\d{1,2}$/.test(e.key)||e.ctrlKey||e.altKey||e.metaKey) {
      if(!['Control','Alt','Meta','Shift'].includes(e.key))state.flushInput();
      state.emit('key',state.normalize(el),{key:e.key,ctrl:e.ctrlKey,alt:e.altKey,meta:e.metaKey,shift:e.shiftKey});
    }
  });
  const historyEvent=()=>{if(state.mode==='record')state.emit('history',null,{url:location.href});};
  for(const method of ['pushState','replaceState']) {
    const original=history[method];
    history[method]=function(...args){const result=original.apply(this,args);historyEvent();return result;};
  }
  addEventListener('popstate',historyEvent,true);
  const carry=()=>{state.flushInput();};
  addEventListener('pagehide',carry,true);
  addEventListener('beforeunload',carry,true);
  state.scanRoots=()=>{
    const scan=root=>{
      for(const el of root.querySelectorAll('*')) {
        if(!el.shadowRoot)continue;
        const shadow=el.shadowRoot;
        if(!state.observedRoots.has(shadow)) {
          state.observedRoots.add(shadow);
          for(const [type,handler] of state.handlers) shadow.addEventListener(type,event=>{if(!event.composed)handler(event);},true);
        }
        scan(shadow);
      }
    };
    scan(document);
  };
  const rootsChanged=new MutationObserver(()=>state.scanRoots());
  rootsChanged.observe(document,{childList:true,subtree:true});
  const originalAttachShadow=Element.prototype.attachShadow;
  Element.prototype.attachShadow=function(options) {
    const root=originalAttachShadow.call(this,options);
    if(options.mode==='closed')state.closedHosts.add(this);
    else state.scanRoots();
    return root;
  };
}
window.__flowtape.scanRoots();
