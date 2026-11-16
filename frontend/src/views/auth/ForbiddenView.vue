<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()
</script>
<template><main style="padding: 48px"><el-result icon="warning" title="没有访问权限" sub-title="当前账号无权进入此页面。如需调整角色，请联系管理员。"><template #extra><el-button @click="router.back()">返回上一页</el-button><el-button type="primary" @click="router.push('/jobs')">返回岗位管理</el-button></template></el-result></main></template>
