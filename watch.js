#!/usr/bin/env node
const chokidar = require('chokidar')
const execSync = require('child_process').execSync
const _ = require('lodash')
const watcher = chokidar.watch(['**/*'], {
  ignoreInitial: true,
})

watcher.on(
  'all',
  _.debounce(() => {
    console.log('copying...')
    execSync('./copy.sh', { stdio: 'inherit' })
  }, 2000)
)
