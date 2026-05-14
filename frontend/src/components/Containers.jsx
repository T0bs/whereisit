import React, { useState } from 'react'

export default function Containers({ api, containers, onChange }){
  const [name, setName] = useState('')
  const [width, setWidth] = useState('')
  const [height, setHeight] = useState('')
  const [depth, setDepth] = useState('')

  const create = async (e) =>{
    e.preventDefault()
    await fetch(`${api}/containers/`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, width: width?Number(width):null, height: height?Number(height):null, depth: depth?Number(depth):null})
    })
    setName(''); setWidth(''); setHeight(''); setDepth('')
    onChange()
  }

  return (
    <div className="card">
      <h3>Containers</h3>
      <form onSubmit={create}>
        <input placeholder="Name" value={name} onChange={e=>setName(e.target.value)} required />
        <input placeholder="Width" value={width} onChange={e=>setWidth(e.target.value)} />
        <input placeholder="Height" value={height} onChange={e=>setHeight(e.target.value)} />
        <input placeholder="Depth" value={depth} onChange={e=>setDepth(e.target.value)} />
        <button type="submit">Add Container</button>
      </form>

      <div>
        <label className="small">Containers</label>
        <select className="list-select" multiple size={20}>
          {containers.map(c => (
            <option key={c.id} value={c.id}>{c.name} — {c.width || ''}×{c.height || ''}×{c.depth || ''}</option>
          ))}
        </select>
      </div>
    </div>
  )
}
