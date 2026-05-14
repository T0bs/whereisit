import React, { useState } from 'react'

export default function Search({ api, onSelect }){
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])

  const search = async (e)=>{
    e.preventDefault()
    const res = await fetch(`${api}/items/`)
    const items = await res.json()
    const filtered = items.filter(i => i.name.toLowerCase().includes(q.toLowerCase()) || (i.tags || []).some(t=>t.includes(q)))
    setResults(filtered)
  }

  return (
    <div className="card">
      <h3>Search Items</h3>
      <form onSubmit={search}>
        <input placeholder="Search by name or tag" value={q} onChange={e=>setQ(e.target.value)} />
        <button type="submit">Search</button>
      </form>
      <div className="list">
        {results.map(r=> <div key={r.id} className="list-item">{r.name} — {r.tags?.join(', ')}</div>)}
      </div>
    </div>
  )
}
