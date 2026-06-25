import { useState } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'

export default function Login() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      params.append('username', email)
      params.append('password', password)
      const res = await axios.post('http://localhost:8000/api/auth/login', params)
      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('role', res.data.role)
      localStorage.setItem('role_label', res.data.role_label || '')
      localStorage.setItem('is_admin', res.data.is_admin ? '1' : '0')
      localStorage.setItem('permissions', JSON.stringify(res.data.permissions || {}))
      localStorage.setItem('name', res.data.name)
      router.push('/dashboard')
    } catch (e) {
      setError('Неверный email или пароль')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{minHeight:'100vh',display:'flex',alignItems:'center',justifyContent:'center',background:'var(--bg)'}}>
      <div style={{background:'var(--card)',padding:'40px',borderRadius:'16px',width:'380px',boxShadow:'0 4px 24px rgba(0,0,0,0.08)'}}>
        <h1 style={{fontSize:'24px',fontWeight:'600',marginBottom:'8px'}}>Финансовый учёт</h1>
        <p style={{color:'var(--muted)',fontSize:'16px',marginBottom:'28px'}}>Войдите в систему</p>

        <div style={{marginBottom:'16px'}}>
          <label style={{fontSize:'15px',color:'var(--muted)',display:'block',marginBottom:'6px'}}>Email</label>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
            style={{width:'100%',padding:'10px 14px',borderRadius:'8px',border:'1px solid var(--border)',fontSize:'16px',outline:'none'}}
            placeholder="admin@company.ru"
          />
        </div>

        <div style={{marginBottom:'24px'}}>
          <label style={{fontSize:'15px',color:'var(--muted)',display:'block',marginBottom:'6px'}}>Пароль</label>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
            style={{width:'100%',padding:'10px 14px',borderRadius:'8px',border:'1px solid var(--border)',fontSize:'16px',outline:'none'}}
            placeholder="••••••••"
          />
        </div>

        {error && <p style={{color:'var(--danger)',fontSize:'15px',marginBottom:'16px'}}>{error}</p>}

        <button
          onClick={handleLogin}
          disabled={loading}
          style={{width:'100%',padding:'12px',background:'var(--primary)',color:'white',border:'none',borderRadius:'8px',fontSize:'16px',fontWeight:'500',cursor:'pointer'}}
        >
          {loading ? 'Вход...' : 'Войти'}
        </button>
      </div>
    </div>
  )
}