const fs = require('fs');
const path = require('path');
const DATA_FILE = path.join(__dirname, 'data.json');

function load() {
  try {
    return JSON.parse(fs.readFileSync(DATA_FILE, 'utf-8'));
  } catch (e) {
    // 初始结构:为 data_models 里的每个集合建一个数组,seq 做自增 id。
    // 例如有 todos、users 两个集合就写 { todos: [], users: [], seq: 0 }
    return { employees: [], seq: 0 };
  }
}
function save(data) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2), 'utf-8');
}
module.exports = { load, save };