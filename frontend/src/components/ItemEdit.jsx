import React, { useEffect, useState } from 'react'

export default function ItemEdit({ api, itemId, onSaved, onCancel }){
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [data, setData] = useState(null)

  useEffect(()=>{
    if(!itemId) return
    let mounted = true
    const load = async ()=>{
      setLoading(true)
      try{
        if(itemId === 'new'){
          const json = { name: '', description: null, tags: [] }
          if(mounted) setData(json)
        }else{
          const res = await fetch(`${api}/items/${itemId}`)
          if(!res.ok) throw new Error('fetch failed')
          const json = await res.json()
          if(mounted) setData(json)
        }
      }catch(e){
        if(mounted) setData(null)
      }finally{ if(mounted) setLoading(false) }
    }
    load()
    return ()=>{ mounted = false }
  },[api, itemId])

  const change = (k, v)=>{
    setData(prev => ({...prev, [k]: v}))
  }

  const save = async ()=>{
    if(!data) return
    setSaving(true)
    try{
      const payload = {
        name: data.name,
        description: data.description ?? null,
        tags: data.tags ?? [],
      }
      if(itemId === 'new'){
        const res = await fetch(`${api}/items/`, {
          method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
        })
        if(!res.ok) throw new Error('create failed')
        const created = await res.json()
        if(onSaved) onSaved(created)
      }else{
        const res = await fetch(`${api}/items/${itemId}`, {
          method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
        })
        if(!res.ok) throw new Error('save failed')
        const json = await res.json()
        if(onSaved) onSaved(json)
      }
    }catch(e){
      console.error(e)
    }finally{ setSaving(false) }
  }

  if(!itemId) return null

  return (
    <aside className="right-pane">
      <div className="pane-header">Item Edit</div>
      {loading && <div>Loading...</div>}
      {!loading && !data && <div>Item not found</div>}
      {data && (
        <div className="form-table">
          <table>
            <tbody>
              <tr>
                {itemId !== 'new' ? <><th>ID</th><td>{data.id}</td></> : <><th>ID</th><td>—</td></>}
              </tr>
              <tr>
                <th>Name</th>
                <td><input value={data.name ?? ''} onChange={e=>change('name', e.target.value)} /></td>
              </tr>
              <tr>
                <th>Description</th>
                <td><textarea value={data.description ?? ''} onChange={e=>change('description', e.target.value)} /></td>
              </tr>
              <tr>
                <th>Tags</th>
                <td><input value={(data.tags || []).join(', ')} onChange={e=>change('tags', e.target.value.split(',').map(s=>s.trim()).filter(Boolean))} placeholder="comma-separated" /></td>
              </tr>
            </tbody>
          </table>
          <div style={{marginTop:8}}>
            <button onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
            <button onClick={onCancel} style={{marginLeft:8}}>Cancel</button>
          </div>
        </div>
      )}
    </aside>
  )
}
