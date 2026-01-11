# 📊 Polymarket Builder Dashboard

Beautiful real-time analytics dashboard for Polymarket builders to track trading activity, volume, and user engagement.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/vikions/opipolix-builder-dashboard)

## ✨ Features

- 📈 Real-time statistics (volume, trades, users, transactions)
- 📊 Interactive charts with daily trends
- ⏱️ All-time and 24-hour performance tracking
- 📅 Daily & weekly breakdowns
- 🔄 Auto-refresh every 5 minutes

## 🚀 Quick Deploy

1. **Click** the "Deploy with Vercel" button above
2. **Fork** the repository to your GitHub
3. **Add** these environment variables in Vercel:
   - `BUILDER_API_KEY`
   - `BUILDER_SECRET`
   - `BUILDER_PASS_PHRASE`
4. **Deploy** and your dashboard is live! 🎉

### Get Your API Credentials

Get your Polymarket Builder API credentials from the [Polymarket Builder Portal](https://polymarket.com).

## 📁 Project Structure
```
├── api/stats.py          # Backend API
├── public/index.html     # Frontend dashboard
├── requirements.txt      # Dependencies
└── vercel.json          # Config
```

## 🛠️ Local Development
```bash
# Clone
git clone https://github.com/vikions/opipolix-builder-dashboard.git
cd opipolix-builder-dashboard

# Install dependencies
pip install -r requirements.txt

# Create .env file
echo "BUILDER_API_KEY=your_key
BUILDER_SECRET=your_secret
BUILDER_PASS_PHRASE=your_passphrase" > .env

# Run locally
vercel dev
```

Open `http://localhost:3000`

## 🐛 Troubleshooting

**No data showing?**
- Check environment variables in Vercel: Settings → Environment Variables
- Verify API credentials are correct
- Make sure you have trades in your builder account

**500 Error?**
- Check logs: Deployments → Latest → View Function Logs
- Test API: `https://your-project.vercel.app/api/stats?hours=24`

## 🤝 Contributing

PRs welcome! Fork, create a feature branch, and submit a PR.

## 📝 License

MIT License - see [LICENSE](LICENSE)

---

⭐ **Star this repo if it helps you!**

Made with ❤️ for Polymarket Builders by [vikions](https://github.com/vikions)