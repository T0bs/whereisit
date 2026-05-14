import React, { useEffect, useState } from 'react'

export default function Tags({ api, onChange }){
  const [tags, setTags] = useState([])
  const [name, setName] = useState('')
  const [selectedIds, setSelectedIds] = useState([])

  const load = async ()=>{
    const res = await fetch(`${api}/tags/`)
    setTags(await res.json())
  }

  useEffect(()=>{ load() }, [])

  const create = async (e)=>{
    e.preventDefault()
    if(!name) return
    await fetch(`${api}/tags/`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})})
    setName('')
    await load()
    onChange && onChange()
  }

  const remove = async (id)=>{
    if(!confirm('Delete tag?')) return
    await fetch(`${api}/tags/${id}`, {method:'DELETE'})
    await load()
    onChange && onChange()
  }

  return (
    <div className="card">
      <h3>Tags</h3>
      <form onSubmit={create} className="tag-form">
        <input placeholder="New tag name" value={name} onChange={e=>setName(e.target.value)} />
        <button type="submit">Add Tag</button>
      </form>

      <div>
        <label className="small">Tags</label>
        <select className="list-select" multiple size={20} onChange={e=>{
          const vals = Array.from(e.target.selectedOptions).map(o=>Number(o.value))
          setSelectedIds(vals)
        }}>
          {tags.map(t=> (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <div style={{marginTop:8}}>
          <button className="small" onClick={async ()=>{
            if(selectedIds.length===0) return
            if(!confirm('Delete selected tag(s)?')) return
            for(const id of selectedIds){ await fetch(`${api}/tags/${id}`, {method:'DELETE'}) }
            await load(); onChange && onChange(); setSelectedIds([])
          }}>Delete Selected</button>
        </div>
      </div>
    </div>
  )
}
