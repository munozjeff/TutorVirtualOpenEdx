export default function Header({ userInfo, config, onTabChange, activeTab, onClearHistory }) {
    const isInstructor = userInfo?.user_role === 'instructor' || userInfo?.user_role === 'admin'

    return (
        <>
            <header className="header">
                <div className="header__brand">
                    <div className="header__avatar">🎓</div>
                    <div>
                        <div className="header__title">{config?.tutor_name || 'Tutor Virtual'}</div>
                        {config?.topic && (
                            <div className="header__subtitle">{config.topic}</div>
                        )}
                    </div>
                </div>

                <div className="header__user">
                    {userInfo && (
                        <>
                            <span className="header__user-name">{userInfo.user_name}</span>
                            <span className={`badge badge--${isInstructor ? 'instructor' : 'student'}`}>
                                {isInstructor ? 'Instructor' : 'Estudiante'}
                            </span>
                        </>
                    )}

                    <div className="header__actions">
                        <button
                            className="icon-btn"
                            onClick={onClearHistory}
                            title="Limpiar conversación"
                        >
                            🗑️
                        </button>
                    </div>
                </div>
            </header>

            {isInstructor && (
                <nav className="tab-bar">
                    <button className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => onTabChange('chat')}>💬 Chat</button>
                    <button className={`tab-btn ${activeTab === 'config' ? 'active' : ''}`} onClick={() => onTabChange('config')}>⚙️ Configuración</button>
                    <button className={`tab-btn ${activeTab === 'admin' ? 'active' : ''}`} onClick={() => onTabChange('admin')}>🔗 Registrar Bloques</button>
                </nav>
            )}
        </>
    )
}
