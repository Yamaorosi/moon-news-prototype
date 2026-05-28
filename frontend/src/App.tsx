import { useState, useEffect } from 'react'
import './App.css'

interface NewsItem {
  title: string;
  url: string;
  body: string;
  poem?: string;
}

// 開発環境と本番環境でAPIの向き先を切り替える
const API_BASE = import.meta.env.DEV 
  ? 'http://localhost:8000' 
  : 'https://moon-news-prototype-production.up.railway.app';

// 詩を個別に読み込むためのコンポーネント
function PoemSection({ title, initialPoem }: { title: string, initialPoem?: string }) {
  const [poem, setPoem] = useState<string | null>(initialPoem || null);
  const [loading, setLoading] = useState(!initialPoem);

  useEffect(() => {
    if (initialPoem) return;

    const fetchPoem = async () => {
      try {
        // リクエストを分散させるためにランダムな待機（1〜3秒）を入れる
        const delay = Math.random() * 2000 + 1000;
        await new Promise(resolve => setTimeout(resolve, delay));

        const response = await fetch(`${API_BASE}/poem?title=${encodeURIComponent(title)}`);
        const json = await response.json();
        setPoem(json.poem);
      } catch (err) {
        setPoem("月は雲に隠れてしまいました...");
      } finally {
        setLoading(false);
      }
    };
    fetchPoem();
  }, [title, initialPoem]);

  return (
    <div className="poem-card">
      {loading ? (
        <p className="poem-text loading-text">月が詩を綴っています...</p>
      ) : (
        <p className="poem-text fade-in" style={{ whiteSpace: 'pre-wrap' }}>{poem}</p>
      )}
    </div>
  );
}

function App() {
  const [newsList, setNewsList] = useState<NewsItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ニュースを先に持ってくる
  const fetchNews = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/news`);
      if (!response.ok) {
        throw new Error('サーバからニュースを取ってこれんかった');
      }
      const json = await response.json();
      setNewsList(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : '予期せぬエラー');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNews();
  }, []);

  return (
    <div className="moon-container">
      <header>
        <h1>月下読酌</h1>
      </header>

      <main>
        {loading ? (
          <div className="loading">ニュースを読み込んでいます...</div>
        ) : error ? (
          <div className="error">{error}</div>
        ) : newsList ? (
          <div className="content-fade-in timeline">
            {newsList.map((news, index) => (
              <div key={index} className="poetic-card">
                <section className="poem-section">
                  <PoemSection title={news.title} initialPoem={news.poem} />
                </section>

                <section className="news-section">
                  <div className="news-card">
                    <div className="news-content">
                      <h3>{news.title}</h3>
                      <p className="news-desc" style={{ whiteSpace: 'pre-wrap' }}>{news.body}</p>
                      <a href={news.url} target="_blank" rel="noopener noreferrer" className="news-link">記事全文を読む</a>
                    </div>
                  </div>
                </section>
              </div>
            ))}

            <button className="refresh-button" onClick={fetchNews}>
              次の杯を。
            </button>
          </div>
        ) : null}
      </main>

      <footer>
        <p>© 2026 月下読酌</p>
        <div className="admin-links">
          <a href={`${API_BASE}/analysis`} target="_blank" rel="noopener noreferrer">分析結果 (JSON)</a>
          <span> | </span>
          <a href={`${API_BASE}/history`} target="_blank" rel="noopener noreferrer">保存履歴 (JSON)</a>
        </div>
      </footer>
    </div>
  )
}

export default App
