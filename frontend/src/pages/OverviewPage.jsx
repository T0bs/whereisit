import React, { useEffect, useState } from 'react'
import DetailModal from '../components/DetailModal'

export default function OverviewPage({ api, onEdit }){
  const [containers, setContainers] = useState([])
  const [items, setItems] = useState([])
  const [tags, setTags] = useState([])
  const [placements, setPlacements] = useState([])

  const load = async ()=>{
    try{
      const [rc, ri, rt, rp] = await Promise.all([
        fetch(`${api}/containers/`).then(r=>r.json()),
        fetch(`${api}/items/`).then(r=>r.json()),
        fetch(`${api}/tags/`).then(r=>r.json()),
        fetch(`${api}/placements/`).then(r=>r.json()),
      ])
      setContainers(rc)
      setItems(ri)
      setTags(rt)
      setPlacements(rp)
    }catch(e){
      setContainers([]); setItems([]); setTags([])
    }
  }

  useEffect(()=>{ load() }, [])

  const [modalOpen, setModalOpen] = useState(false)
  const [modalTitle, setModalTitle] = useState('')
  const [modalData, setModalData] = useState(null)

  const openDetail = async (type, id) => {
    // if a parent handler wants to open an edit form (e.g., right side), prefer that
    if(onEdit && (type === 'containers' || type === 'items')){
      onEdit(type, id)
      return
    }
    setModalOpen(true)
    setModalData(null)
    setModalTitle(`${type[0].toUpperCase()+type.slice(1)} ${id}`)
    try{
      const res = await fetch(`${api}/${type}/${id}`)
      const json = await res.json()
      setModalData(json)
    }catch(e){
      setModalData({error: 'Failed to load'})
    }
  }

  return (
    <div className="card">
      <h2>Overview</h2>

      <div className="overview-tables stacked">
        <div className="overview-table">
          <h3>Containers ({containers.length})</h3>
          <table>
            <thead>
              <tr><th style={{width:'10%'}}>ID</th><th style={{width:'60%'}}>Name</th><th style={{width:'30%'}}>Info</th></tr>
            </thead>
            <tbody className="table-body">
              {containers.map(c => (
                <tr key={c.id} onClick={()=>openDetail('containers', c.id)}>
                  <td>{c.id}</td>
                  <td><strong>{c.name}</strong></td>
                  <td className="small">items: {(() => {
                    // compute recursive item count for this container
                    try{
                      if(!containers || !placements) return '0'
                      const childMap = {}
                      containers.forEach(x=> childMap[x.id] = [])
                      containers.forEach(x=> { if(x.parent_id) { if(childMap[x.parent_id]) childMap[x.parent_id].push(x.id) } })
                      // gather all descendant IDs including self
                      const stack = [c.id]
                      const ids = new Set()
                      while(stack.length){
                        const cur = stack.pop()
                        if(ids.has(cur)) continue
                        ids.add(cur)
                        const ch = childMap[cur] || []
                        for(const cid of ch) stack.push(cid)
                      }
                      // count placements whose container_id is in ids
                      let cnt = 0
                      for(const p of placements){ if(ids.has(p.container_id)) cnt += (p.quantity || 1) }
                      return cnt
                    }catch(e){ return '0' }
                  })()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{marginTop:6}}><button className="small" onClick={()=>{ if(onEdit) onEdit('containers','new') }}>New</button></div>
        </div>

        <div className="overview-table">
          <h3>All items ({items.length})</h3>
          <table>
            <thead>
              <tr><th style={{width:'10%'}}>ID</th><th style={{width:'60%'}}>Name</th><th style={{width:'30%'}}>Details</th></tr>
            </thead>
            <tbody className="table-body">
              {items.map(i => (
                <tr key={i.id} onClick={()=>openDetail('items', i.id)}>
                  <td>{i.id}</td>
                  <td><strong>{i.name}</strong></td>
                  <td className="small">{(() => {
                    try{
                      if(!placements || !containers) return '—'
                      const names = new Set()
                      for(const p of placements){
                        if(p.item_id === i.id){
                          const c = containers.find(x => x.id === p.container_id)
                          if(c && c.name) names.add(c.name)
                        }
                      }
                      return names.size ? Array.from(names).join(', ') : '—'
                    }catch(e){ return '—' }
                  })()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{marginTop:6}}><button className="small" onClick={()=>{ if(onEdit) onEdit('items','new') }}>New</button></div>
        </div>

        <div className="overview-table">
          <h3>Tags ({tags.length})</h3>
          <table>
            <thead>
              <tr><th style={{width:'10%'}}>ID</th><th style={{width:'60%'}}>Tag</th><th style={{width:'30%'}}>Info</th></tr>
            </thead>
            <tbody className="table-body">
              {tags.map(t => (
                <tr key={t.id} onClick={()=>openDetail('tags', t.id)}>
                  <td>{t.id}</td>
                  <td>{t.name}</td>
                  <td className="small"></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{marginTop:6}}><button className="small" onClick={()=>{ if(onEdit) onEdit && onEdit('tags','new') }}>New</button></div>
        </div>
      </div>
      <DetailModal open={modalOpen} onClose={()=>setModalOpen(false)} title={modalTitle} data={modalData} />
    </div>
  )
}
