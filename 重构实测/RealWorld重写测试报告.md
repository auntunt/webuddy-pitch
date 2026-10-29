# RealWorld .NET 转 Java + 达梦：测试结果

源：官方 ASP.NET Core 版 a51468ca04；对照：官方 Spring Boot 版 ee17e31aaf。合并后的 Java 代码在 realworld-net 仓库的 tmh-java-all 分支。

## 每一部分

| 部分 | 单号 | 状态 | 用时（分） | 新增 Java / XML | 改到 java/ 以外 | 构建 | 诊断 | 合并 |
|---|---|---|---|---|---|---|---|---|
| 0 骨架 | RW-1 | closed | 19.4 | 18 / 2 | — | pass | unknown | 已合入 |
| 1 文章标签 | RW-2 | doing | 29.9 | 3 / 1 | — | skip | fail | 已合入 |
| 2 用户资料查询 | RW-3 | verify | 40.6 | 3 / 1 | — | pass | unknown | 已合入 |
| 3 文章收藏 | RW-4 | verify | 23.9 | 4 / 1 | — | pass | unknown | 已合入 |
| 4 用户关注 | RW-5 | verify | 29.9 | 4 / 1 | — | pass | unknown | 已合入 |
| 5 文章评论 | RW-6 | verify | 37.5 | 4 / 1 | — | pass | unknown | 已合入 |
| 6 用户账户与身份认证 | RW-7 | verify | 23.6 | 6 / 1 | — | pass | unknown | 已合入 |
| 7 文章管理 | RW-8 | verify | 26.2 | 5 / 1 | — | pass | unknown | 已合入 |

## 接口覆盖（规范 19 个接口；改出来的 18 个，参考版本 19 个）

| 接口 | 改出来的 | 参考版本 |
|---|---|---|
| POST /api/users/login | UsersController.java | UsersApi.java |
| POST /api/users | UsersController.java | UsersApi.java |
| GET /api/user | UsersController.java | CurrentUserApi.java |
| PUT /api/user | UsersController.java | CurrentUserApi.java |
| GET /api/profiles/{username} | **缺** | ProfileApi.java |
| POST /api/profiles/{username}/follow | FollowersController.java | ProfileApi.java |
| DELETE /api/profiles/{username}/follow | FollowersController.java | ProfileApi.java |
| GET /api/articles/feed | ArticlesController.java | ArticlesApi.java |
| GET /api/articles | ArticlesController.java | ArticlesApi.java |
| POST /api/articles | ArticlesController.java | ArticlesApi.java |
| GET /api/articles/{slug} | ArticlesController.java | ArticleApi.java |
| PUT /api/articles/{slug} | ArticlesController.java | ArticleApi.java |
| DELETE /api/articles/{slug} | ArticlesController.java | ArticleApi.java |
| GET /api/articles/{slug}/comments | CommentsController.java | CommentsApi.java |
| POST /api/articles/{slug}/comments | CommentsController.java | CommentsApi.java |
| DELETE /api/articles/{slug}/comments/{id} | CommentsController.java | CommentsApi.java |
| POST /api/articles/{slug}/favorite | FavoritesController.java | ArticleFavoriteApi.java |
| DELETE /api/articles/{slug}/favorite | FavoritesController.java | ArticleFavoriteApi.java |
| GET /api/tags | TagsController.java | TagsApi.java |

每一部分的改动和参考版本对应文件的清单在 compare/ 目录。
