import { CheerioCrawler } from 'crawlee';
import express from 'express';

const app = express();
app.use(express.json());

app.post('/scrape', async (req, res) => {
    const { platform, query } = req.body;
    const results = [];

    const crawler = new CheerioCrawler({
        async requestHandler({ request, $, enqueueLinks }) {
            $('a').each((_, el) => {
                const href = $(el).attr('href');
                if (href && href.includes(platform)) {
                    results.push({
                        url: href,
                        title: $(el).text().trim(),
                        snippet: '',
                        source: 'crawlee_service',
                    });
                }
            });
        },
    });

    await crawler.run([`https://duckduckgo.com/?q=site:${platform}.com+${encodeURIComponent(query)}`]);

    res.json({ results });
});

app.listen(4000, () => {
    console.log('Crawlee service running on http://localhost:4000');
});
