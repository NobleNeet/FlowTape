/* Shared Recorder/Player DOM semantics. No application DOM mutation. */
const FT = {
  norm(v) { return String(v ?? '').replace(/\s+/g, ' ').trim(); },
  role(el) {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit.split(/\s+/)[0];
    const tag = el.localName, type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') return ({button:'button',submit:'button',reset:'button',checkbox:'checkbox',radio:'radio',file:'button',search:'searchbox'}[type] || 'textbox');
    return ({h1:'heading',h2:'heading',h3:'heading',h4:'heading',h5:'heading',h6:'heading',tr:'row',table:'table',form:'form',dialog:'dialog',img:'img',li:'listitem',ul:'list',ol:'list'}[tag] || '');
  },
  label(el) {
    if (el.labels && el.labels.length) return this.norm([...el.labels].map(x => x.innerText || x.textContent).join(' '));
    const wrap = el.closest('label');
    return wrap ? this.norm(wrap.innerText || wrap.textContent) : '';
  },
  contentName(el) {
    const parts=[];
    for(const node of el.childNodes) {
      if(node.nodeType === Node.TEXT_NODE) {parts.push(node.textContent);continue;}
      if(node.nodeType !== Node.ELEMENT_NODE || node.matches('script,style,[hidden],[aria-hidden="true"],[data-flowtape-overlay]'))continue;
      const style=getComputedStyle(node);
      if(style.display==='none'||style.visibility==='hidden')continue;
      parts.push(node.getAttribute('aria-label') || (node.localName==='img' ? node.getAttribute('alt') : this.contentName(node)) || '');
    }
    return this.norm(parts.join(' '));
  },
  name(el) {
    const ids = el.getAttribute('aria-labelledby');
    if (ids) {
      const root = el.getRootNode();
      const s = this.norm(ids.split(/\s+/).map(id => root.getElementById?.(id)?.textContent || '').join(' '));
      if (s) return s;
    }
    const aria = el.getAttribute('aria-label'); if (aria) return this.norm(aria);
    const label = this.label(el); if (label) return label;
    if (el.localName === 'img') return this.norm(el.getAttribute('alt'));
    if (el.localName === 'input' && ['submit','button','reset'].includes(el.type)) return this.norm(el.value);
    return this.contentName(el) || this.norm(el.getAttribute('title') || '');
  },
  visible(el) {
    if (!el.isConnected) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse') return false;
    for (let node=el; node; node=node.parentElement || node.getRootNode()?.host) {
      if (node.hidden || node.getAttribute('aria-hidden') === 'true') return false;
      const ancestorStyle=getComputedStyle(node);
      if (ancestorStyle.display === 'none' || ['hidden','collapse'].includes(ancestorStyle.visibility)) return false;
    }
    return !!(el.getClientRects().length);
  },
  enabled(el) { return !el.matches(':disabled') && el.getAttribute('aria-disabled') !== 'true'; },
  editable(el) { return this.enabled(el) && !el.readOnly && (el.matches('textarea') || (el.localName === 'input' && ['text','search','email','url','tel','password','number','date','time','datetime-local','month','week'].includes(el.type)) || el.isContentEditable); },
  testid(el) { return ['data-testid','data-test','data-cy','data-qa'].map(k=>el.getAttribute(k)).find(Boolean) || ''; },
  all(scope) { return [...scope.querySelectorAll('*')].filter(el=>!el.closest('[data-flowtape-overlay]')); },
  frames(scope=document) {
    const result=[];
    for(const el of this.all(scope)) {
      if(el.matches('iframe,frame')) result.push(el);
      if(el.shadowRoot) result.push(...this.frames(el.shadowRoot));
    }
    return result;
  },
  match(el, s) {
    return Object.entries(s).every(([k,v]) => {
      if (k === 'role') return this.role(el) === v;
      if (k === 'name') return this.name(el) === this.norm(v);
      if (k === 'text') return this.norm(el.innerText || el.textContent) === this.norm(v);
      if (k === 'label') return el.matches('input,textarea,select,button,output,meter,progress') && this.label(el) === this.norm(v);
      if (k === 'testid') return ['data-testid','data-test','data-cy','data-qa'].some(attr=>el.getAttribute(attr)===v);
      if (k === 'id') return el.id === v;
      return false;
    });
  },
  semantic(scope, s) { return this.all(scope).filter(el => this.match(el,s)); },
  pageCondition(condition) {
    const [op,val]=Object.entries(condition)[0];
    if(op==='url') {
      const [mode,expected]=Object.entries(val)[0];
      return mode==='equals'?location.href===expected:mode==='contains'?location.href.includes(expected):location.href.startsWith(expected);
    }
    if(op==='exists')return this.semantic(document,val).length>0;
    if(op==='all')return val.every(x=>this.pageCondition(x));
    if(op==='any')return val.some(x=>this.pageCondition(x));
    return !this.pageCondition(val);
  },
  captureEvidence(el, snapshot, documentId, pageConditions) {
    const candidates=[];
    for(const attribute of ['data-testid','data-test','data-cy','data-qa']) {
      if(snapshot.attributes[attribute])candidates.push({by:'testid',value:snapshot.attributes[attribute]});
    }
    if(el.id)candidates.push({by:'id',value:el.id});
    if(snapshot.role && snapshot.name)candidates.push({by:'role',role:snapshot.role,name:snapshot.name});
    if(snapshot.label)candidates.push({by:'label',value:snapshot.label});
    if(snapshot.attributes.name)candidates.push({by:'name',value:snapshot.attributes.name});
    if(snapshot.attributes.placeholder)candidates.push({by:'placeholder',value:snapshot.attributes.placeholder});
    if(snapshot.text && snapshot.text.length<80)candidates.push({by:'text',value:snapshot.text,exact:true});
    const tag=snapshot.tag,type=snapshot.attributes.type,role=snapshot.role;
    let kind=type==='file'?'file':tag==='input' && ['checkbox','radio'].includes(type)?type:tag==='input'?'input':
      ['textarea','select'].includes(tag)?tag:['button','link','checkbox','radio','tab'].includes(role)?role:'element';
    if(tag==='input' && role==='button' && type!=='file')kind='button';
    const expect=['button','link','checkbox','radio','tab'].includes(kind)?{role}:{tag};
    if(['input','textarea'].includes(kind) || snapshot.editable)expect.editable=true;
    if(kind==='input' && type)expect.input_type=type;
    const locate=candidates.filter(loc=>{
      const matches=this.locate(el.getRootNode(),loc).filter(e=>this.accepts(e,expect,'click',kind));
      return matches.length===1 && matches[0]===el;
    });
    return {document_id:documentId,locate,page_conditions:pageConditions,
      pages:Object.entries(pageConditions).filter(([id,condition])=>this.pageCondition(condition)).map(([id])=>id)};
  },
  locate(scope, loc) {
    const by = loc.by, value = loc.value;
    if (by === 'css') return [...scope.querySelectorAll(value)];
    if (by === 'xpath') {
      const result = document.evaluate(value, scope, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      return Array.from({length:result.snapshotLength}, (_,i)=>result.snapshotItem(i)).filter(x=>x instanceof Element);
    }
    if (by === 'relative') {
      const anchors = this.semantic(scope,loc.anchor);
      const scopes = [...new Set(anchors.map(anchor => {
        if (loc.relation === 'row') return anchor.closest('[role="row"]') || anchor.closest('tr');
        if (loc.relation === 'dialog') return anchor.closest('[role="dialog"], [role="alertdialog"]') || anchor.closest('dialog');
        if (loc.relation === 'form') return anchor.closest('form');
        return anchor;
      }).filter(Boolean))];
      if (scopes.length !== 1) return scopes.length ? {ambiguous:true} : [];
      const base = scopes[0];
      return base ? this.semantic(base,loc.target) : [];
    }
    return this.all(scope).filter(el => {
      if (by === 'testid') return ['data-testid','data-test','data-cy','data-qa'].some(attr=>el.getAttribute(attr)===value);
      if (by === 'id') return el.id === value;
      if (by === 'name') return el.getAttribute('name') === value;
      if (by === 'label') return el.matches('input,textarea,select,button,output,meter,progress') && this.label(el) === this.norm(value);
      if (by === 'placeholder') return el.getAttribute('placeholder') === value;
      if (by === 'attribute') return el.getAttribute(loc.name) === value;
      if (by === 'role') return this.role(el) === loc.role && (!loc.name || this.name(el) === this.norm(loc.name));
      if (by === 'text') {
        const actual = this.norm(el.innerText || el.textContent);
        return loc.exact === false ? actual.includes(this.norm(value)) : actual === this.norm(value);
      }
      return false;
    });
  },
  accepts(el, expect = {}, action = '', kind = '') {
    if(['button','link','checkbox','radio','tab','menu'].includes(kind) && this.role(el)!==kind)return false;
    if(['input','textarea','select'].includes(kind) && el.localName!==kind)return false;
    if(kind==='file' && !(el.localName==='input' && el.type==='file'))return false;
    if (expect.tag && el.localName !== expect.tag.toLowerCase()) return false;
    if (expect.role && this.role(el) !== expect.role) return false;
    if (expect.input_type && el.getAttribute('type') !== expect.input_type) return false;
    if ('visible' in expect && this.visible(el) !== expect.visible) return false;
    if ('enabled' in expect && this.enabled(el) !== expect.enabled) return false;
    if ('editable' in expect && this.editable(el) !== expect.editable) return false;
    for (const [k,v] of Object.entries(expect.attributes || {})) if (el.getAttribute(k) !== v) return false;
    if (['click','double_click','key'].includes(action) && (!this.visible(el) || !this.enabled(el))) return false;
    if (action==='hover' && !this.visible(el))return false;
    if (action === 'input' && !this.editable(el)) return false;
    if (action === 'select' && el.localName !== 'select') return false;
    if (action === 'upload' && !(el.localName === 'input' && el.type === 'file')) return false;
    return true;
  },
  identity(el) {
    if (this.testid(el)) return {testid:this.testid(el)};
    if (el.id && !/[0-9]{6,}|[a-f0-9]{8}-|^(react|ember|mui)[-_]/i.test(el.id)) return {id:el.id};
    if (this.role(el) && this.name(el)) return {role:this.role(el),name:this.name(el)};
    const text=this.norm(el.innerText || el.textContent);
    return text && text.length < 80 ? {text} : null;
  },
  hostSelector(el) {
    if (el.id) return '#'+CSS.escape(el.id);
    if (this.testid(el)) {
      const attr=['data-testid','data-test','data-cy','data-qa'].find(k=>el.getAttribute(k));
      return '['+attr+'='+JSON.stringify(el.getAttribute(attr))+']';
    }
    return el.localName;
  },
  shadowPath(el) {
    const path=[];
    for(let root=el.getRootNode(); root.host; root=root.host.getRootNode()) path.unshift({shadow:{css:this.hostSelector(root.host)}});
    return path;
  },
  snapshot(el) {
    const relations=[];
    for(const [relation,selector] of [['row','tr,[role=row]'],['dialog','dialog,[role=dialog],[role=alertdialog]'],['form','form']]) {
      const scope=el.closest(selector); if(!scope) continue;
      let anchor=this.identity(scope);
      if (relation === 'row') {
        const cell=[...scope.querySelectorAll('th,td,[role=cell],[role=rowheader]')].find(x=>!x.contains(el) && this.norm(x.innerText || x.textContent));
        if(cell) anchor={text:this.norm(cell.innerText || cell.textContent)};
      }
      if(anchor) relations.push({relation,anchor});
    }
    return {tag:el.localName, type:el.getAttribute('type'), role:this.role(el), name:this.name(el), label:this.label(el), text:this.norm(el.innerText || el.textContent).slice(0,200), visible:this.visible(el), enabled:this.enabled(el), editable:this.editable(el), relations, shadow_path:this.shadowPath(el), attributes:Object.fromEntries(['id','name','placeholder','autocomplete','data-testid','data-test','data-cy','data-qa','href','type','data-action','class'].filter(k=>el.hasAttribute(k)).map(k=>[k,el.getAttribute(k)]))};
  }
};
