const express = require('express');
const cors = require('cors');
const multer = require('multer');
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const { v4: uuidv4 } = require('uuid');

const app = express();
const PORT = process.env.PORT || 3003;
const PROJECTS_DIR = path.join(__dirname, 'projects');

// 中间件
app.use(cors());
app.use(express.json());
app.use('/projects', express.static(path.join(__dirname, 'projects')));

// 确保项目目录存在
if (!fs.existsSync(PROJECTS_DIR)) {
  fs.mkdirSync(PROJECTS_DIR, { recursive: true });
}

// 文件上传配置
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const sessionId = req.body.sessionId || 'default';
    const sessionDir = path.join(PROJECTS_DIR, sessionId, 'uploads');
    fs.mkdirSync(sessionDir, { recursive: true });
    cb(null, sessionDir);
  },
  filename: (req, file, cb) => {
    const uniqueName = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}${path.extname(file.originalname)}`;
    cb(null, uniqueName);
  }
});

const upload = multer({
  storage: storage,
  limits: { fileSize: 100 * 1024 * 1024 } // 100MB
});

// 会话存储
const sessions = new Map();

// 首页
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 上传文件 API
app.post('/api/upload', upload.array('files'), (req, res) => {
  const sessionId = req.body.sessionId;
  const files = req.files.map(f => ({
    name: f.originalname,
    path: '/projects/' + sessionId + '/uploads/' + f.filename,
    thumbnail: f.mimetype.startsWith('image/') ? '/projects/' + sessionId + '/uploads/' + f.filename : null,
    type: f.mimetype,
    size: f.size,
    savedAt: new Date().toISOString()
  }));
  res.json({ files });
});

// 流式对话 API
app.post('/api/chat', upload.array('files'), async (req, res) => {
  const { message, sessionId } = req.body;
  const uploadedFiles = req.files || [];

  // 设置 SSE 头
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'none');

  try {
    // 获取或创建会话
    let session = sessions.get(sessionId);
    if (!session) {
      session = { id: sessionId, history: [], createdAt: new Date().toISOString() };
      sessions.set(sessionId, session);
    }

    // 创建会话项目目录
    const sessionDir = path.join(PROJECTS_DIR, sessionId);
    const uploadsDir = path.join(sessionDir, 'uploads');
    const outputsDir = path.join(sessionDir, 'outputs');
    fs.mkdirSync(uploadsDir, { recursive: true });
    fs.mkdirSync(outputsDir, { recursive: true });

    // 记录用户消息
    const userMsg = {
      role: 'user',
      content: message,
      files: uploadedFiles.map(f => ({
        name: f.originalname,
        path: `/projects/${sessionId}/uploads/${f.filename}`,
        type: f.mimetype,
        size: f.size
      })),
      timestamp: new Date().toISOString()
    };
    session.history.push(userMsg);

    // 保存对话到文件
    const chatLogPath = path.join(sessionDir, 'conversation.md');
    saveConversation(session, chatLogPath);

    // 构建消息内容
    let fullMessage = message;

    // 添加上传文件信息
    if (uploadedFiles.length > 0) {
      const fileList = uploadedFiles.map(f => `- ${f.originalname} (${f.mimetype}, ${(f.size / 1024).toFixed(1)}KB)`).join('\n');
      fullMessage = `用户上传了以下文件:\n${fileList}\n\n问题: ${message}`;
    }

    // 添加历史上下文
    if (session.history.length > 1) {
      const recentHistory = session.history.slice(-6, -1);
      const context = recentHistory.map(h => {
        let text = `**${h.role === 'user' ? '用户' : '助手'}** (${h.timestamp}):\n${h.content}`;
        if (h.files && h.files.length > 0) {
          text += `\n附件: ${h.files.map(f => f.name).join(', ')}`;
        }
        return text;
      }).join('\n\n---\n\n');
      fullMessage = `## 对话历史\n\n${context}\n\n---\n\n## 当前问题\n\n${fullMessage}`;
    }

    // 发送开始信号
    res.write(`data: ${JSON.stringify({ type: 'start' })}\n\n`);

    // 构建环境变量
    const env = {
      ...process.env,
      ANTHROPIC_AUTH_TOKEN: 'sk-cp-MWmY5LHRY9viQ_ShLvpRaIm5EU56NntUFM5f-HigNQ2-WSqAz0krDgEhUzhMIf2XCjQwyUWfFHchNfGRiTtjQ20JoHqnyt9XHYTsUhYy9fCkDrZb-_DhgPo',
      ANTHROPIC_BASE_URL: 'https://api.minimaxi.com/anthropic',
      ANTHROPIC_MODEL: 'MiniMax-M2.5',
      API_TIMEOUT_MS: '300000'
    };

    // 执行 Claude
    const escapedMessage = fullMessage.replace(/'/g, "'\\''");
    const command = `claude --print -p '${escapedMessage}'`;
    console.log('Executing:', command);

    let output = '';
    try {
      output = execSync(command, {
        env: env,
        encoding: 'utf8',
        timeout: 180000,
        maxBuffer: 10 * 1024 * 1024
      });
    } catch (execError) {
      console.error('Exec error:', execError.message);
      output = execError.stdout || execError.message;
    }

    // 发送内容
    res.write(`data: ${JSON.stringify({ type: 'content', content: output })}\n\n`);

    // 保存 AI 回复
    const assistantMsg = {
      role: 'assistant',
      content: output,
      timestamp: new Date().toISOString()
    };
    session.history.push(assistantMsg);
    saveConversation(session, chatLogPath);

    // 检查是否有生成的文件需要保存
    const outputFiles = checkForOutputFiles(output, outputsDir);
    outputFiles.forEach(file => {
      res.write(`data: ${JSON.stringify({ type: 'file', file })}\n\n`);
    });

    // 发送结束
    const sessionName = `会话 ${sessionId.substr(0, 8)}`;
    res.write(`data: ${JSON.stringify({ type: 'end', content: output, sessionName })}\n\n`);
    res.end();

  } catch (error) {
    console.error('Error:', error);
    res.write(`data: ${JSON.stringify({ type: 'error', error: error.message })}\n\n`);
    res.end();
  }
});

// 保存对话到文件
function saveConversation(session, chatLogPath) {
  let md = `# 对话记录\n\n`;
  md += `会话ID: ${session.id}\n`;
  md += `创建时间: ${session.createdAt}\n`;
  md += `---\n\n`;

  session.history.forEach((msg, i) => {
    md += `## ${i + 1}. ${msg.role === 'user' ? '用户' : 'Claude'}\n`;
    md += `时间: ${msg.timestamp}\n`;
    if (msg.files && msg.files.length > 0) {
      md += `附件:\n`;
      msg.files.forEach(f => md += `- ${f.name}\n`);
    }
    md += `\n${msg.content}\n\n`;
  });

  fs.writeFileSync(chatLogPath, md, 'utf8');
}

// 检查输出中是否有文件需要保存
function checkForOutputFiles(output, outputsDir) {
  const files = [];
  // 简化处理：检查是否有文件路径提及
  // 实际实现中可以解析 AI 输出中的文件信息
  return files;
}

// 获取会话历史
app.get('/api/sessions/:sessionId', (req, res) => {
  const { sessionId } = req.params;
  const session = sessions.get(sessionId);
  if (session) {
    res.json({ history: session.history, sessionName: `会话 ${sessionId.substr(0, 8)}` });
  } else {
    // 尝试从文件加载
    const chatLogPath = path.join(PROJECTS_DIR, sessionId, 'conversation.md');
    if (fs.existsSync(chatLogPath)) {
      res.json({ history: [], sessionName: `会话 ${sessionId.substr(0, 8)}`, loadedFromFile: true });
    } else {
      res.json({ history: [] });
    }
  }
});

// 创建新会话
app.post('/api/sessions', (req, res) => {
  const sessionId = uuidv4();
  sessions.set(sessionId, { id: sessionId, history: [], createdAt: new Date().toISOString() });
  res.json({ sessionId });
});

// 删除会话
app.delete('/api/sessions/:sessionId', (req, res) => {
  const { sessionId } = req.params;
  sessions.delete(sessionId);
  res.json({ success: true });
});

// 健康检查
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Web Claude Code 服务已启动: http://0.0.0.0:${PORT}`);
  console.log(`项目目录: ${PROJECTS_DIR}`);
});
