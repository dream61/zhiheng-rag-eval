import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'../tests/e2e',workers:1,timeout:60000,
 use:{channel:'chrome',baseURL:'http://127.0.0.1:15173',trace:'retain-on-failure',screenshot:'only-on-failure'},
 webServer:[
  {command:'../.venv/bin/python ../backend/manage.py runserver 127.0.0.1:18000 --noreload',url:'http://127.0.0.1:18000/api/health/',reuseExistingServer:false},
  {command:'npm run dev -- --port 15173 --strictPort',url:'http://127.0.0.1:15173',reuseExistingServer:false,env:{VITE_BACKEND_URL:'http://127.0.0.1:18000'}}
 ]
});
