import { useState } from 'react'
import Header from './components/Header'
import StudentView from './views/StudentView'
import InstructorView from './views/InstructorView'
import RegistrationPanel from './views/RegistrationPanel'
import { useChat } from './hooks/useChat'

export default function App() {
    const {
        messages, isLoading, error, userInfo, config,
        isInitialized, sendMessage, clearHistory, setConfig,
    } = useChat()

    const [activeTab, setActiveTab] = useState('chat')

    const isInstructor =
        userInfo?.user_role === 'instructor' || userInfo?.user_role === 'admin'

    // Admin setup mode: access via http://localhost:5173/?admin=1 before LTI launch
    const isAdminMode = new URLSearchParams(window.location.search).get('admin') === '1'

    // ── Admin mode: direct access for setup (no LTI session required) ──────────
    if (isAdminMode) {
        return (
            <div className="app">
                <header className="header">
                    <div className="header__brand">
                        <div className="header__avatar">🎓</div>
                        <div><div className="header__title">Tutor Virtual — Administración</div></div>
                    </div>
                </header>
                <RegistrationPanel />
            </div>
        )
    }

    // ── Loading state ──────────────────────────────────────────────────────────
    if (!isInitialized) {
        return (
            <div className="app">
                <div className="loading-screen">
                    <div className="spinner" />
                    <span>Iniciando tutor…</span>
                </div>
            </div>
        )
    }

    // ── Session error (not launched from Open edX) ────────────────────────────
    if (!userInfo && error) {
        return (
            <div className="app">
                <div className="loading-screen">
                    <span style={{ fontSize: '48px' }}>🎓</span>
                    <h2 style={{ fontSize: '18px', fontWeight: 600 }}>Tutor Virtual LTI</h2>
                    <div className="error-banner" style={{ maxWidth: '480px' }}>
                        ⚠️ {error}
                    </div>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px', textAlign: 'center', maxWidth: '380px' }}>
                        Esta aplicación debe abrirse desde Open edX a través de un bloque LTI.
                    </p>
                </div>
            </div>
        )
    }

    // ── Main app ───────────────────────────────────────────────────────────────
    return (
        <div className="app">
            <Header
                userInfo={userInfo}
                config={config}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                onClearHistory={clearHistory}
            />

            {isInstructor && activeTab === 'config' ? (
                <InstructorView
                    config={config}
                    userInfo={userInfo}
                    onConfigUpdate={setConfig}
                    onClearHistory={clearHistory}
                />
            ) : (
                <StudentView
                    messages={messages}
                    isLoading={isLoading}
                    error={error}
                    onSend={sendMessage}
                    userInfo={userInfo}
                    config={config}
                    onClearHistory={clearHistory}
                />
            )}
        </div>
    )
}
