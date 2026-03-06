import puppeteer, { Browser, Page } from 'puppeteer'

import { config } from './config'

const LAUNCH_ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--use-gl=swiftshader', '--disable-software-rasterizer']

export class BrowserPool {
    private browser: Browser | null = null
    private usageCount = 0
    private activePages = 0
    private recycling: Promise<void> | null = null

    constructor(private recycleAfter: number = config.browserRecycleAfter) {}

    async launch(): Promise<void> {
        if (this.browser) {
            return
        }
        this.browser = await puppeteer.launch({
            headless: config.headless,
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
            args: LAUNCH_ARGS,
        })
        this.usageCount = 0
    }

    async getPage(): Promise<Page> {
        // Wait if a recycle is in progress
        if (this.recycling) {
            await this.recycling
        }

        if (!this.browser) {
            await this.launch()
        }

        this.activePages++
        this.usageCount++
        return await this.browser!.newPage()
    }

    async releasePage(page: Page): Promise<void> {
        try {
            await page.close()
        } catch {
            // Page may already be closed
        }
        this.activePages--

        if (this.usageCount >= this.recycleAfter && this.activePages === 0) {
            await this.recycle()
        }
    }

    async recycle(): Promise<void> {
        if (this.recycling) {
            return this.recycling
        }
        this.recycling = this._doRecycle()
        await this.recycling
        this.recycling = null
    }

    private async _doRecycle(): Promise<void> {
        await this.shutdown()
        await this.launch()
    }

    async shutdown(): Promise<void> {
        if (this.browser) {
            try {
                await this.browser.close()
            } catch {
                // Ignore cleanup errors
            }
            this.browser = null
        }
    }

    get stats(): { usageCount: number; activePages: number } {
        return { usageCount: this.usageCount, activePages: this.activePages }
    }
}
