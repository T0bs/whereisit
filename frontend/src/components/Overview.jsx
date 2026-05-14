import React from 'react'

export default function Overview({ items, containers }){
  return (
    <div className="card">
      <h3>Overview</h3>
      <div>
        <strong>Containers:</strong> {containers.length}
      </div>
      <div>
        <strong>Items:</strong> {items.length}
      </div>
      <div style={{marginTop:8}}>
        <strong>Map:</strong>
        <div style={{border:'1px dashed #ccc', padding:8, marginTop:8}}>
          <select className="list-select" size={6} style={{width:'100%'}}>
            {containers.map(c => (
              <option key={c.id} value={c.id}>{c.name} — {(items.filter(i=>i.id)).length} items</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}
