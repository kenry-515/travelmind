import { useState } from 'react';
import { X, Copy, Check, Link2, Share2, Image } from 'lucide-react';
import { toast } from './Toast';

interface ShareModalProps {
  isOpen: boolean;
  onClose: () => void;
  itineraryId: string;
  title: string;
}

export function ShareModal({ isOpen, onClose, itineraryId, title }: ShareModalProps) {
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleGenerateLink = async () => {
    setIsGenerating(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/agent/itinerary/share/${itineraryId}?expires_days=30`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail?.message || '创建分享链接失败');
      }

      const data = await response.json();
      // Build full URL
      const fullUrl = `${window.location.origin}${data.share_url}`;
      setShareUrl(fullUrl);
      toast.success('分享链接已创建！');
    } catch (err) {
      setError(err instanceof Error ? err.message : '未知错误');
      toast.error('创建分享链接失败');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      toast.success('链接已复制到剪贴板！');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('复制失败，请手动选择链接');
    }
  };

  const handleDownloadPoster = () => {
    // Placeholder for poster generation
    // Will implement canvas-based poster creation later
    toast.info('海报生成功能开发中...');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div 
        className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Share2 className="text-brand-600" size={24} />
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">分享行程</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:bg-slate-800 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            分享「<span className="font-medium text-slate-900 dark:text-slate-100">{title}</span>」给朋友
          </p>

          {!shareUrl && !isGenerating && (
            <button
              onClick={handleGenerateLink}
              className="w-full btn-primary flex items-center justify-center gap-2"
            >
              <Link2 size={18} />
              生成分享链接
            </button>
          )}

          {isGenerating && (
            <div className="flex items-center justify-center gap-2 py-3 text-slate-500 dark:text-slate-400">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
              <span className="text-sm">正在生成链接...</span>
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
              {error}
            </div>
          )}

          {shareUrl && (
            <div className="space-y-3">
              {/* URL Display */}
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 p-3">
                <div className="flex items-center gap-2">
                  <Link2 size={16} className="shrink-0 text-slate-400 dark:text-slate-500" />
                  <input
                    type="text"
                    readOnly
                    value={shareUrl}
                    className="flex-1 bg-transparent text-sm text-slate-700 dark:text-slate-300 focus:outline-none"
                    onClick={(e) => (e.target as HTMLInputElement).select()}
                  />
                  <button
                    onClick={handleCopy}
                    className="shrink-0 rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-white dark:bg-slate-900 hover:text-brand-600 transition-colors"
                    title="复制链接"
                  >
                    {copied ? <Check size={16} className="text-green-500" /> : <Copy size={16} />}
                  </button>
                </div>
              </div>

              <p className="text-xs text-slate-500 dark:text-slate-400">
                链接有效期 30 天，点击即可查看完整行程
              </p>

              {/* Actions */}
              <div className="flex gap-2">
                <button
                  onClick={handleCopy}
                  className="flex-1 btn-secondary flex items-center justify-center gap-2"
                >
                  <Copy size={16} />
                  复制链接
                </button>
                <button
                  onClick={handleDownloadPoster}
                  className="flex-1 btn-secondary flex items-center justify-center gap-2"
                >
                  <Image size={16} />
                  生成海报
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-6 text-center">
          <button
            onClick={onClose}
            className="text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:text-slate-300 transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
