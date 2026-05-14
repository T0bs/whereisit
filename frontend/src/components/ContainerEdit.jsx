import React, { useEffect, useState } from 'react'

export default function ContainerEdit({ api, containerId, onSaved, onCancel }){
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [data, setData] = useState(null)
  const [containersList, setContainersList] = useState([])
  const [viewsList, setViewsList] = useState([])

  const load = async ()=>{
    setLoading(true)
    try{
      let json = null
      if(containerId === 'new'){
        json = {
          name: '', width: null, height: null, depth: null,
          gps_lat: null, gps_lng: null, parent_id: null, view_id: null
        }
        setData(json)
      }else{
        const res = await fetch(`${api}/containers/${containerId}`)
        if(res.ok){ json = await res.json(); setData(json) }
        else { setData(null) }
      }

      // fetch containers and views for selects
      try{
        const [allContainersRes, allViewsRes] = await Promise.all([
          fetch(`${api}/containers/`),
          fetch(`${api}/views/`),
        ])
        const allContainers = allContainersRes.ok ? await allContainersRes.json() : []
        const allViews = allViewsRes.ok ? await allViewsRes.json() : []
        setContainersList(Array.isArray(allContainers) ? allContainers.filter(c=>c.id !== containerId) : [])
        setViewsList(Array.isArray(allViews) ? allViews : [])
      }catch(e){
        setContainersList([])
        setViewsList([])
      }
    }catch(e){
      setData(null)
    }finally{ setLoading(false) }
  }

  useEffect(()=>{ if(containerId) load() }, [containerId])

  const change = (k, v)=> setData(d => ({...d, [k]: v}))

  const save = async ()=>{
    setSaving(true)
    try{
      const payload = {
        name: data.name,
        width: data.width,
        height: data.height,
        depth: data.depth,
        gps_lat: data.gps_lat,
        gps_lng: data.gps_lng,
        parent_id: data.parent_id,
        view_id: data.view_id,
      }
      if(containerId === 'new'){
        const res = await fetch(`${api}/containers/`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})
        if(!res.ok) throw new Error('create failed')
        const created = await res.json()
        onSaved && onSaved(created)
      }else{
        const res = await fetch(`${api}/containers/${containerId}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})
        if(!res.ok) throw new Error('update failed')
        const updated = await res.json()
        onSaved && onSaved(updated)
      }
    }catch(e){
      console.error(e)
      alert('Failed to save')
    }finally{ setSaving(false) }
  }

  if(loading) return <div className="card"><div className="small">Loading container...</div></div>
  if(!data) return <div className="card"><div className="small">Container not found.</div></div>

  return (
    <div className="card">
      <h3>{containerId === 'new' ? 'New container' : 'Edit container'}</h3>
      {containerId !== 'new' && <div className="small">ID: {data.id}</div>}

      <table className="form-table">
        <tbody>
          <tr>
            <th>Name</th>
            <td><input value={data.name||''} onChange={e=>change('name', e.target.value)} placeholder="Name" /></td>
          </tr>
          <tr>
            <th>Width</th>
            <td><input type="number" step="any" value={data.width ?? ''} onChange={e=>change('width', e.target.value === '' ? null : Number(e.target.value))} placeholder="Width" /></td>
          </tr>
          <tr>
            <th>Height</th>
            <td><input type="number" step="any" value={data.height ?? ''} onChange={e=>change('height', e.target.value === '' ? null : Number(e.target.value))} placeholder="Height" /></td>
          </tr>
          <tr>
            <th>Depth</th>
            <td><input type="number" step="any" value={data.depth ?? ''} onChange={e=>change('depth', e.target.value === '' ? null : Number(e.target.value))} placeholder="Depth" /></td>
          </tr>
          <tr>
            <th>GPS Latitude</th>
            <td><input type="number" step="any" value={data.gps_lat ?? ''} onChange={e=>change('gps_lat', e.target.value === '' ? null : Number(e.target.value))} placeholder="GPS lat" /></td>
          </tr>
          <tr>
            <th>GPS Longitude</th>
            <td><input type="number" step="any" value={data.gps_lng ?? ''} onChange={e=>change('gps_lng', e.target.value === '' ? null : Number(e.target.value))} placeholder="GPS lng" /></td>
          </tr>
          <tr>
            <th>Parent</th>
            <td>
              <select value={data.parent_id ?? ''} onChange={e=>change('parent_id', e.target.value === '' ? null : Number(e.target.value))}>
                <option value="">— none —</option>
                {containersList.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </td>
          </tr>
          <tr>
            <th>View</th>
            <td>
              <select value={data.view_id ?? ''} onChange={e=>change('view_id', e.target.value === '' ? null : Number(e.target.value))}>
                <option value="">(default)</option>
                {viewsList.map(v => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </select>
            </td>
          </tr>
        </tbody>
      </table>

      <div style={{display:'flex', gap:8, marginTop:8}}>
        <button onClick={save} disabled={saving}>{saving? 'Saving...':'Save'}</button>
        <button className="secondary" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}
