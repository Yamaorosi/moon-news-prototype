import { useState, useEffect } from 'react'
import './App.css'

interface NewsItem {
  title: string;
  source: string;
  url: string;
  publishedAt: string;
  description: string;
  imageUrl: string;
}

// 開発環境と本番環境でAPIの向き先を切り替える
const API_BASE = import.meta.env.DEV ? 'http://localhost:8000' : '';

// 詩を個別に読み込むためのコンポーネント
function PoemSection({ title }: { title: string }) {
  const [poem, setPoem] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPoem = async () => {
      try {
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
  }, [title]);

  return (
    <div className="poem-card">
      {loading ? (
        <p className="poem-text loading-text">月が詩を綴っています...</p>
      ) : (
        <p className="poem-text fade-in">{poem}</p>
      )}
    </div>
  );
}

function App() {
  const [newsList, setNewsList] = useState<NewsItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ニュースだけを先に持ってくる
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
          <div className="loading">月下...</div>
        ) : error ? (
          <div className="error">{error}</div>
        ) : newsList ? (
          <div className="content-fade-in timeline">
            {newsList.map((news, index) => (
              <div key={index} className="poetic-card">
                <section className="poem-section">
                  <PoemSection title={news.title} />
                </section>

                <section className="news-section">
                  <div className="news-card">
                    {news.imageUrl && (
                      <img src={news.imageUrl} alt="news" className="news-image" />
                    )}
                    <div className="news-content">
                      <h3>{news.title}</h3>
                      <p className="news-meta">{news.source} | {new Date(news.publishedAt).toLocaleDateString()}</p>
                      <p className="news-desc">{news.description}</p>
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
