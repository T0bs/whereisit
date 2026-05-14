import React, { useState } from 'react'

export default function Placements({ api, items, containers, onChange }){
  const [itemId, setItemId] = useState('')
  const [containerId, setContainerId] = useState('')
  const [quantity, setQuantity] = useState(1)

  const create = async (e)=>{
    e.preventDefault()
    await fetch(`${api}/placements/`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({item_id: Number(itemId), container_id: Number(containerId), quantity: Number(quantity)})
    })
    setItemId(''); setContainerId(''); setQuantity(1)
    onChange()
  }

  return (
    <div className="card">
      <h3>Placements</h3>
      <form onSubmit={create}>
        <select value={itemId} onChange={e=>setItemId(e.target.value)} required>
          <option value="">Select item</option>
          {items.map(i=> <option key={i.id} value={i.id}>{i.name}</option>)}
        </select>
        <select value={containerId} onChange={e=>setContainerId(e.target.value)} required>
          <option value="">Select container</option>
          {containers.map(c=> <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input type="number" min="1" value={quantity} onChange={e=>setQuantity(e.target.value)} />
        <button type="submit">Assign</button>
      </form>
    </div>
  )
}
