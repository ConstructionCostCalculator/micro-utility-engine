# SolveEase Six-Stage Pipeline

This ZIP contains six independent, runnable Flask repositories connected by versioned JSON handoffs:
1. Global Utility Scanner
2. Value-to-Money Filter
3. Professional Engagement
4. Approved Task Executor
5. Quality Delivery
6. Payment Verification

This is a tested starter baseline, not proof of real demand, clients, sales or revenue. Scanner scores are heuristics; submitted evidence is not independently validated by the filter; execution has a small allow-list; payment verification fails closed until a real provider adapter is implemented. Configure strong API tokens before public deployment.

## Deployment
Create six GitHub repositories using the folder names, copy each folder's contents into its matching repository, and deploy each as its own Render web service. Each folder has `render.yaml`, `.env.example`, `README.md`, and a smoke test. Configure `NEXT_STAGE_URL`/`NEXT_STAGE_TOKEN` for each handoff after testing each stage separately. Keep a persistent disk mounted at `/var/data`.
