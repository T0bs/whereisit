import React, { useEffect, useState, useRef } from 'react'
let AsyncCreatable = null
try{ AsyncCreatable = require('react-select/async-creatable').default }catch(e){ AsyncCreatable = null }

export default function Items({ api, items, onChange }){
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [availableTags, setAvailableTags] = useState([])
  const [selectedOptions, setSelectedOptions] = useState([])

  const loadTags = async (input) =>{
    try{
      const q = input ? `?q=${encodeURIComponent(input)}&limit=20` : '?limit=20'
      const res = await fetch(`${api}/tags/${q}`)
      const data = await res.json()
      return data.map(t=>({value:t.name,label:t.name}))
    }catch(e){
      return []
    }
  }

  useEffect(()=>{ /* keep availableTags for fallback */ }, [])

  const loaderRef = useRef()
  if(!loaderRef.current){
    // debounced loader that batches rapid calls into one fetch
    loaderRef.current = function(input){
      return new Promise((resolve)=>{
        if(loaderRef.current._timer) clearTimeout(loaderRef.current._timer)
        loaderRef.current._timer = setTimeout(async ()=>{
          const opts = await loadTags(input)
          resolve(opts)
        }, 300)
      })
    }
  }

  const create = async (e) =>{
    e.preventDefault()
    const tags = selectedOptions.map(o=>o.value)
    await fetch(`${api}/items/`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, description, tags})
    })
    setName(''); setDescription(''); setSelectedOptions([])
    onChange()
    loadTags()
  }

  return (
    <div className="card">
      <h3>Items</h3>
      <form onSubmit={create}>
        <input placeholder="Name" value={name} onChange={e=>setName(e.target.value)} required />
        <textarea placeholder="Description" value={description} onChange={e=>setDescription(e.target.value)} />

        {AsyncCreatable ? (
          <div className="tags-picker">
            <div className="small">Tags</div>
            <AsyncCreatable
              isMulti
              cacheOptions
              defaultOptions
              loadOptions={loaderRef.current}
              onChange={setSelectedOptions}
              onCreateOption={async (val)=>{
                // create tag in backend then add to selection
                try{
                  await fetch(`${api}/tags/`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name: val})})
                }catch(e){}
                const newOpt = {value: val, label: val}
                setSelectedOptions(prev => Array.isArray(prev)? [...prev, newOpt] : [newOpt])
              }}
              value={selectedOptions}
              placeholder="Type to add or select tags..."
            />
          </div>
        ) : (
          <div className="tags-picker">
            <div className="small">Tags (react-select not installed)</div>
            <input placeholder="Comma separated tags" onChange={e=>setSelectedOptions(e.target.value.split(',').map(s=>({value:s.trim(),label:s.trim()})))} />
          </div>
        )}

        <button type="submit">Add Item</button>
      </form>

      <div>
        <label className="small">Items</label>
        <select className="list-select" multiple size={20}>
          {items.map(it => (
            <option key={it.id} value={it.id}>{it.name} — {it.description || ''}{it.tags && it.tags.length? ` [${it.tags.join(', ')}]` : ''}</option>
          ))}
        </select>
      </div>
    </div>
  )
}
